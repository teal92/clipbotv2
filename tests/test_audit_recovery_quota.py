"""Run against the released snapshot; synthetic accounts and no email/network."""
from fastapi import FastAPI
from fastapi.testclient import TestClient
from server.store import Store
from server.account_recovery import AccountRecovery, build_recovery_router


def make_service(tmp_path):
    store = Store(tmp_path / 'synthetic.db')
    service = AccountRecovery(store, 'https://clipbot.example', config={'enabled': False})
    app = FastAPI()
    app.include_router(build_recovery_router(service))
    return store, service, app


def test_ip_rejected_forgot_attempts_do_not_exhaust_other_users(tmp_path):
    store, service, app = make_service(tmp_path)
    with TestClient(app, client=('198.51.100.1', 5000)) as attacker:
        for _ in range(100):
            assert attacker.post('/api/auth/forgot-password', json={'email': 'missing@example.invalid'}).status_code == 200
    # A fresh user's request should still pass the global admission gate.
    assert service.allow('forgot-global', 100)


def test_ip_rejected_redemptions_do_not_exhaust_other_users(tmp_path):
    store, service, app = make_service(tmp_path)
    data = {'token': 'A' * 43, 'newPassword': 'StrongClipBot!2026'}
    with TestClient(app, client=('198.51.100.1', 5000)) as attacker:
        for _ in range(100):
            attacker.post('/api/auth/reset-password', json=data)
    with TestClient(app, client=('198.51.100.2', 5000)) as other_user:
        # An invalid token from an unrelated IP should be validated (422),
        # rather than globally blocked by the first IP's rejected attempts.
        assert other_user.post('/api/auth/reset-password', json=data).status_code == 422


def test_concurrent_limits_charge_all_scopes_only_for_admitted_requests(tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    store,service,_=make_service(tmp_path)
    with ThreadPoolExecutor(max_workers=8) as pool:
        admitted=list(pool.map(lambda _:service.allow_many([('caller',3,900),('global',100,900)]),range(30)))
    assert sum(admitted)==3
    with store.connection() as db:
        assert db.execute("SELECT COUNT(*) FROM recovery_attempts WHERE scope='global'").fetchone()[0]==3
