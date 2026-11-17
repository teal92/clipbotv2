import time
from fastapi.testclient import TestClient
from server.app import create_app
from server.legal import POLICY_VERSION
from test_companion import setup,report

def test_direct_start_requires_verified_policies_connections_and_live_payment(setup):
    store,uid,token,scouts,c=setup
    app=create_app(store,origin='http://testserver')
    c.report(token,{**report(),'version':'0.2.7-beta'})
    with TestClient(app) as client:
        raw,_=store.new_session(uid);client.cookies.set('clipbot_session',raw)
        headers={'Origin':'http://testserver','X-CSRF-Token':client.get('/api/account').json()['csrfToken']}
        assert client.post('/api/companion/control',json={'running':True},headers=headers).status_code==428
        with store.connection() as db:
            db.execute('INSERT INTO email_verification VALUES(?,?)',(uid,1))
            db.execute('INSERT INTO legal_acceptances VALUES(?,?,?)',(uid,POLICY_VERSION,1))
        assert client.post('/api/companion/control',json={'running':True},headers=headers).status_code==409
        app.state.oauth.status=lambda *args:{'connected':True,'status':'connected','monitoringReady':True}
        assert client.post('/api/companion/control',json={'running':True},headers=headers).status_code==409
        assert client.post('/api/companion/control',json={'running':False},headers=headers).status_code==200

def test_configured_owner_keeps_private_start_workflow(setup,monkeypatch):
    store,uid,token,scouts,c=setup
    monkeypatch.setenv('CLIPBOT_ADMIN_USER_ID',uid)
    app=create_app(store,origin='http://testserver')
    c.report(token,{**report(),'version':'0.2.7-beta'})
    with TestClient(app) as client:
        raw,_=store.new_session(uid);client.cookies.set('clipbot_session',raw)
        headers={'Origin':'http://testserver','X-CSRF-Token':client.get('/api/account').json()['csrfToken']}
        assert client.post('/api/companion/control',json={'running':True},headers=headers).status_code==200

def test_verified_customer_can_start_with_owned_live_coverage_and_connection(setup):
    store,uid,token,scouts,c=setup
    app=create_app(store,origin='http://testserver')
    store.billing_mode='live';app.state.billing.live=True
    app.state.oauth.status=lambda *args:{'connected':True,'status':'connected','monitoringReady':True}
    with store.connection() as db:
        db.execute('INSERT INTO email_verification VALUES(?,?)',(uid,1))
        db.execute('INSERT INTO legal_acceptances VALUES(?,?,?)',(uid,POLICY_VERSION,1))
        db.execute('INSERT INTO billing_state VALUES(?,?,?,?,?,?,?,?)',(uid,'sub_live_owned','cus_live_owned','starter','active',time.time()+3600,450,'owned'))
        db.execute("INSERT INTO billing_modes VALUES('state',?,'live')",(uid,))
    c.report(token,{**report(),'version':'0.2.7-beta'})
    with TestClient(app) as client:
        raw,_=store.new_session(uid);client.cookies.set('clipbot_session',raw)
        headers={'Origin':'http://testserver','X-CSRF-Token':client.get('/api/account').json()['csrfToken']}
        assert client.post('/api/companion/control',json={'running':True},headers=headers).status_code==200
