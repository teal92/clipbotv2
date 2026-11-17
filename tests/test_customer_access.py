import re
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from server.store import Store
from server.legal import POLICY_VERSION


@pytest.fixture
def setup(tmp_path):
    from server.customer_access import CustomerAccess, build_customer_access_router
    store = Store(tmp_path / 'access.db')
    a = store.create_user('customer@example.com', 'LongPassword!2026', 'Customer')
    b = store.create_user('other@example.com', 'OtherPassword!2026', 'Other')
    sent = []
    access = CustomerAccess(store, 'https://clipbot.example', config={'enabled': True, 'sender': 'support@example.com'}, transport=lambda message: sent.append(message))
    app = FastAPI()
    def current(request, write=False):
        session = store.session(request.cookies.get('clipbot_session', ''))
        if not session: raise HTTPException(401)
        if write and request.headers.get('x-csrf-token') != session['csrf']: raise HTTPException(403)
        return session
    app.include_router(build_customer_access_router(access, current))
    client = TestClient(app, client=('198.51.100.1', 5000))
    token, csrf = store.new_session(a)
    client.cookies.set('clipbot_session', token)
    return store, a, b, access, sent, client, {'x-csrf-token': csrf}


def secret(sent):
    return re.search(r'#token=([A-Za-z0-9_-]+)', sent[-1].get_content()).group(1)


def test_verification_stored_recipient_hash_and_single_use(setup):
    store, a, b, access, sent, client, headers = setup
    response = client.post('/api/account/request-verification', json={}, headers=headers)
    assert response.status_code == 200 and sent[-1]['To'] == 'customer@example.com'
    token = secret(sent)
    assert len(token) == 43 and token not in response.text
    assert '/verify-email.html#token=' in sent[-1].get_content()
    with store.connection() as db:
        assert token not in str([tuple(row) for row in db.execute('SELECT * FROM email_verification_tokens')])
    result = client.post('/api/account/verify-email', json={'token': token}, headers=headers)
    assert result.status_code == 200 and access.readiness(a)['emailVerified']
    assert not access.readiness(b)['emailVerified']
    assert client.post('/api/account/verify-email', json={'token': token}, headers=headers).status_code == 422


def test_verification_wrong_account_does_not_consume_token(setup):
    store, a, b, access, sent, client, headers = setup
    access.request_verification(a, 'ip')
    token = secret(sent)
    assert not access.confirm(b, token)
    assert access.confirm(a, token)


def test_verification_expiry_new_request_invalidates_old(setup):
    store, a, b, access, sent, client, headers = setup
    access.request_verification(a, 'ip')
    old = secret(sent)
    access.request_verification(a, 'ip')
    new = secret(sent)
    assert not access.confirm(a, old)
    with store.connection() as db: db.execute('UPDATE email_verification_tokens SET expires=0')
    assert not access.confirm(a, new)


def test_confirmation_atomic_under_race(setup):
    store, a, b, access, sent, client, headers = setup
    access.request_verification(a, 'ip')
    token = secret(sent)
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sum(pool.map(lambda _: access.confirm(a, token), range(2))) == 1


def test_verification_failed_mail_leaves_no_live_token(setup):
    store, a, b, access, sent, client, headers = setup
    access.transport = lambda message: (_ for _ in ()).throw(RuntimeError('private mail failure'))
    result = client.post('/api/account/request-verification', json={}, headers=headers)
    assert result.status_code == 200 and 'private mail failure' not in result.text
    with store.connection() as db: assert db.execute('SELECT COUNT(*) FROM email_verification_tokens').fetchone()[0] == 0


@pytest.mark.parametrize('origin', ['http://clipbot.example', 'https://clipbot.example/path', 'https://user:pass@clipbot.example', 'https://clipbot.example?x=1'])
def test_verification_requires_secure_canonical_origin(setup, origin):
    store, a, b, access, sent, client, headers = setup
    from server.customer_access import CustomerAccess
    service = CustomerAccess(store, origin, config={'enabled': True, 'sender': 'support@example.com'}, transport=lambda message: sent.append(message))
    service.request_verification(a, 'ip')
    assert not sent and not service.mail_ready


def test_unconfigured_mail_generic_no_token(setup):
    store, a, b, access, sent, client, headers = setup
    access.config['enabled'] = False
    result = client.post('/api/account/request-verification', json={}, headers=headers)
    assert result.status_code == 200 and not sent
    with store.connection() as db: assert db.execute('SELECT COUNT(*) FROM email_verification_tokens').fetchone()[0] == 0


def test_verification_auth_csrf_no_extra_recipient(setup):
    store, a, b, access, sent, client, headers = setup
    assert client.post('/api/account/request-verification', json={}).status_code == 403
    assert client.post('/api/account/request-verification', json={'email': 'attacker@example.com'}, headers=headers).status_code == 422
    assert client.post('/api/account/verify-email', json={'token': 'A'*43, 'user_id': b}, headers=headers).status_code == 422
    client.cookies.clear()
    assert client.post('/api/account/request-verification', json={}, headers=headers).status_code == 401
    assert not sent


def test_quota_atomic_rejections_do_not_charge_other_scopes(setup):
    store, a, b, access, sent, client, headers = setup
    rules = [('ip:one', 2, 900), ('global:test', 100, 900)]
    with ThreadPoolExecutor(max_workers=8) as pool:
        assert sum(pool.map(lambda _: access.admit(rules), range(25))) == 2
    assert access.admit([('ip:two', 2, 900), ('global:test', 100, 900)])
    with store.connection() as db:
        assert db.execute("SELECT COUNT(*) FROM customer_access_attempts WHERE scope='global:test'").fetchone()[0] == 3


def test_policy_current_stale_and_account_readiness(setup):
    store, a, b, access, sent, client, headers = setup
    assert not access.readiness(a)['policyAccepted']
    assert client.post('/api/account/accept-policy', json={'version': 'stale'}, headers=headers).status_code == 422
    assert client.post('/api/account/accept-policy', json={'version': POLICY_VERSION}, headers=headers).status_code == 200
    assert access.readiness(a)['policyAccepted'] and not access.readiness(b)['policyAccepted']
    with store.connection() as db:
        db.execute('DELETE FROM legal_acceptances WHERE user_id=?', (a,))
        db.execute('INSERT INTO legal_acceptances VALUES(?,?,?)', (a, 'stale', 1))
    assert not access.readiness(a)['policyAccepted']


def test_enforcement_prelaunch_owner_exemption_server_only(setup):
    store, a, b, access, sent, client, headers = setup
    access.require_ready(a)  # Existing accounts stay usable until explicit enforcement.
    access.enforce = True
    with pytest.raises(HTTPException) as error: access.require_ready(a)
    assert error.value.status_code == 428
    access.owner_uid = a
    access.require_ready(a)
    with pytest.raises(HTTPException): access.require_ready(b)
    access.request_verification(b, 'ip'); assert access.confirm(b, secret(sent))
    access.accept_policy(b, POLICY_VERSION)
    access.require_ready(b)


def test_reset_and_verification_tokens_are_not_interchangeable(setup):
    store, a, b, access, sent, client, headers = setup
    from server.account_recovery import AccountRecovery
    reset_sent = []
    recovery = AccountRecovery(store, 'https://clipbot.example', config={'enabled': True, 'sender': 'support@example.com'}, transport=lambda message: reset_sent.append(message))
    recovery.request_reset(a)
    reset_token = secret(reset_sent)
    assert not access.confirm(a, reset_token)
    access.request_verification(a, 'ip')
    assert not recovery.redeem(secret(sent), 'NewPassword!2026')


def test_public_registration_gate_fails_closed(setup):
    store, a, b, access, sent, client, headers = setup
    assert not access.public_signup_ready()
    access.edge_verified = True
    assert access.public_signup_ready()
    access.config['enabled'] = False
    assert not access.public_signup_ready()


def test_public_registration_always_enforces_customer_readiness(setup):
    store, a, b, access, sent, client, headers = setup
    from server.customer_access import CustomerAccess
    strict = CustomerAccess(store, 'https://clipbot.example', config=access.config, transport=access.transport,
                            enforce=False, public_signup=True, edge_verified=True, owner_uid='')
    assert strict.enforce and strict.readiness(a)['enforced']
    with pytest.raises(HTTPException): strict.require_ready(a)


def test_changed_stored_email_invalidates_outstanding_verification(setup):
    store, a, b, access, sent, client, headers = setup
    access.request_verification(a, 'ip'); token = secret(sent)
    with store.connection() as db: db.execute('UPDATE users SET email=? WHERE id=?', ('replacement@example.com', a))
    assert not access.confirm(a, token)
    assert not access.readiness(a)['emailVerified']


def test_repeated_policy_acceptance_keeps_first_acceptance_timestamp(setup):
    store, a, b, access, sent, client, headers = setup
    access.accept_policy(a, POLICY_VERSION)
    with store.connection() as db: first = db.execute('SELECT accepted FROM legal_acceptances WHERE user_id=? AND version=?', (a, POLICY_VERSION)).fetchone()[0]
    access.accept_policy(a, POLICY_VERSION)
    with store.connection() as db:
        rows = db.execute('SELECT accepted FROM legal_acceptances WHERE user_id=? AND version=?', (a, POLICY_VERSION)).fetchall()
    assert len(rows) == 1 and rows[0][0] == first


def test_verification_redemption_ip_limit_does_not_exhaust_other_users(setup):
    store, a, b, access, sent, client, headers = setup
    for _ in range(100):
        client.post('/api/account/verify-email', json={'token': 'A' * 43}, headers=headers)
    assert access.admit([('verify-ip:fresh', 10, 900), ('verify-account:fresh', 10, 900), ('verify-global', 100, 900)])
    with store.connection() as db:
        assert db.execute("SELECT COUNT(*) FROM customer_access_attempts WHERE scope='verify-global'").fetchone()[0] == 11


def test_readiness_route_and_policy_require_authentication_csrf(setup):
    store, a, b, access, sent, client, headers = setup
    assert client.get('/api/account/readiness').json()['policyVersion'] == POLICY_VERSION
    assert client.post('/api/account/accept-policy', json={'version': POLICY_VERSION}).status_code == 403
    assert client.post('/api/account/accept-policy', json={'version': POLICY_VERSION, 'enforce': False}, headers=headers).status_code == 422
    client.cookies.clear()
    assert client.get('/api/account/readiness').status_code == 401
