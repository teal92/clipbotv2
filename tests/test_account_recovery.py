import re
import pytest
from server.store import Store

def recovery(tmp_path):
    from server.account_recovery import AccountRecovery
    store=Store(tmp_path/'reset.db');uid=store.create_user('customer@example.com','old-long-password','Customer');sent=[]
    config={'enabled':True,'sender':'support@example.com','recipient':'owner@example.com'}
    return store,uid,AccountRecovery(store,'https://clipbot.example',config=config,transport=lambda message:sent.append(message)),sent

def token(sent):return re.search(r'#token=([A-Za-z0-9_-]+)',sent[-1].get_content()).group(1)

def test_reset_email_exact_stored_recipient_single_use_revoke(tmp_path):
    store,uid,service,sent=recovery(tmp_path);session,_=store.new_session(uid);worker=store.connect_worker(store.new_pairing(uid));other=store.create_user('other@example.com','other-long-password','Other');other_session,_=store.new_session(other)
    result=service.request_reset(uid);secret=token(sent)
    assert sent[-1]['To']=='customer@example.com' and secret not in str(result)
    with store.connection() as db:assert secret not in str([tuple(r) for r in db.execute('SELECT * FROM password_resets')])
    assert service.redeem(secret,'StrongClipBot!2026')
    assert not service.redeem(secret,'SecondClipBot!2026')
    assert store.authenticate('customer@example.com','StrongClipBot!2026')==uid
    assert store.session(session) is None and not store.worker_heartbeat(worker)
    assert store.session(other_session)

def test_expired_invalid_and_newer_request_invalidate(tmp_path):
    store,uid,service,sent=recovery(tmp_path);service.request_reset(uid);old=token(sent)
    with store.connection() as db:db.execute('DELETE FROM recovery_attempts')
    service.request_reset(uid);new=token(sent)
    assert not service.redeem(old,'StrongClipBot!2026')
    with store.connection() as db:db.execute('UPDATE password_resets SET expires=0')
    assert not service.redeem(new,'StrongClipBot!2026')
    assert not service.redeem('not-a-real-token','StrongClipBot!2026')

def test_recovery_setup_and_mail_failure_do_not_leave_tokens(tmp_path):
    from server.account_recovery import RecoveryUnavailable
    store,uid,service,sent=recovery(tmp_path);service.config['enabled']=False
    with pytest.raises(RecoveryUnavailable):service.request_reset(uid)
    service.config['enabled']=True;service.transport=lambda message:(_ for _ in ()).throw(RuntimeError('SMTP failed'))
    with pytest.raises(RecoveryUnavailable):service.request_reset(uid)
    with store.connection() as db:assert db.execute('SELECT COUNT(*) FROM password_resets').fetchone()[0]==0

def test_password_change_invalidates_pending_recovery(tmp_path):
    store,uid,service,sent=recovery(tmp_path);session,_=store.new_session(uid);service.request_reset(uid);secret=token(sent)
    assert store.change_password(uid,store.session(session)['token'],'old-long-password','different-long-password')
    assert not service.redeem(secret,'AttackerClipBot!2026')

def test_public_forgot_is_generic_and_reset_rejects_extra_fields(tmp_path):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from server.account_recovery import build_recovery_router
    store,uid,service,sent=recovery(tmp_path);service.config['enabled']=False
    app=FastAPI();app.include_router(build_recovery_router(service));client=TestClient(app)
    known=client.post('/api/auth/forgot-password',json={'email':'customer@example.com'})
    unknown=client.post('/api/auth/forgot-password',json={'email':'unknown@example.com'})
    assert known.status_code==unknown.status_code==200 and known.json()==unknown.json() and not sent
    assert client.post('/api/auth/reset-password',json={'token':'a'*43,'newPassword':'long-enough-password','user_id':uid}).status_code==422
    assert client.post('/api/auth/reset-password',json={'token':'a'*43,'newPassword':'short'}).status_code==422

def test_recovery_limits_persist_and_single_claim_under_race(tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    from server.account_recovery import AccountRecovery
    store,uid,service,sent=recovery(tmp_path)
    assert service.allow('test-scope',1)
    restarted=AccountRecovery(store,service.origin,config=service.config,transport=service.transport)
    assert not restarted.allow('test-scope',1)
    service.request_reset(uid);secret=token(sent)
    with ThreadPoolExecutor(max_workers=2) as pool:claims=list(pool.map(lambda _:service.redeem(secret,'StrongClipBot!2026'),range(2)))
    assert sum(claims)==1


def test_global_mail_budget_is_fifty_per_day(tmp_path):
    import time
    from server.account_recovery import RecoveryUnavailable
    store,uid,service,sent=recovery(tmp_path)
    with store.connection() as db:
        db.executemany('INSERT INTO recovery_attempts VALUES(?,?)',[('send-global',time.time()-7200)]*50)
    with pytest.raises(RecoveryUnavailable):service.request_reset(uid)
    assert not sent
