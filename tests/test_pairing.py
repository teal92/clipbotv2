from server.legal import POLICY_VERSION
from fastapi.testclient import TestClient
from server.app import create_app
from server.store import Store

def test_pairing_is_single_use_scoped_and_revocable(tmp_path):
    store=Store(tmp_path/'pairing.db');app=create_app(store,origin='http://testserver',local_signup=True)
    with TestClient(app,client=('127.0.0.1',50000)) as web,TestClient(app,client=('127.0.0.1',50001)) as worker:
        web.post('/api/auth/signup',json={'email':'pair@example.com','password':'StrongClipBot!2026','name':'pairuser','termsVersion':POLICY_VERSION},headers={'Origin':'http://testserver'})
        headers={'Origin':'http://testserver','X-CSRF-Token':web.get('/api/account').json()['csrfToken']}
        assert web.post('/api/worker/pairing',headers={'Origin':'http://testserver'}).status_code==403
        code=web.post('/api/worker/pairing',headers=headers).json()['code']
        result=worker.post('/api/worker/connect',json={'code':code},headers={'Origin':'http://testserver'})
        assert result.status_code==201
        token=result.json()['token'];auth={'Origin':'http://testserver','Authorization':'Bearer '+token}
        assert worker.post('/api/worker/connect',json={'code':code},headers={'Origin':'http://testserver'}).status_code==403
        assert worker.post('/api/worker/heartbeat',headers=auth).status_code==200
        assert web.get('/api/workspace').json()['workerConnected'] is True
        assert worker.get('/api/account',headers=auth).status_code==401
        assert web.post('/api/worker/revoke',headers=headers).status_code==200
        assert worker.post('/api/worker/heartbeat',headers=auth).status_code==401
        assert web.get('/api/workspace').json()['workerConnected'] is False

def test_expired_code_cannot_connect(tmp_path):
    store=Store(tmp_path/'expired.db');uid=store.create_user('x@example.com','long-pairing-password','X')
    code=store.new_pairing(uid)
    with store.connection() as db:db.execute('UPDATE worker_pairing SET expires=0')
    assert store.connect_worker(code) is None
