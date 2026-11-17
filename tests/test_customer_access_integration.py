import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from server.app import create_app
from server.store import Store
from server.customer_access import CustomerAccess,require_customer_ready
from server.legal import POLICY_VERSION

def test_public_signup_fails_closed_without_working_mail_and_verified_edge(tmp_path,monkeypatch):
    monkeypatch.setenv('CLIPBOT_PUBLIC_SIGNUP','1')
    app=create_app(Store(tmp_path/'signup.db'),origin='https://testserver',local_signup=False)
    app.state.customer_access.config={'enabled':False}
    with TestClient(app,base_url='https://testserver') as client:
        result=client.post('/api/auth/signup',headers={'Origin':'https://testserver'},json={'email':'new@example.test','name':'new_customer','password':'SafeClipBot!2026','termsVersion':POLICY_VERSION})
        assert result.status_code==503
    with app.state.store.connection() as db:assert db.execute('SELECT COUNT(*) FROM users').fetchone()[0]==0

def test_verified_signup_email_and_policy_gate_precedes_checkout(tmp_path,monkeypatch):
    monkeypatch.setenv('CLIPBOT_PUBLIC_SIGNUP','1');monkeypatch.setenv('CLIPBOT_EDGE_VERIFIED','1')
    store=Store(tmp_path/'signup.db');app=create_app(store,origin='https://testserver',local_signup=False)
    access=app.state.customer_access;sent=[]
    access.config={'enabled':True,'sender':'support@example.test'};access.transport=lambda message:sent.append(message)
    with TestClient(app,base_url='https://testserver') as client:
        body={'email':'new@example.test','name':'new_customer','password':'SafeClipBot!2026','termsVersion':POLICY_VERSION}
        assert client.post('/api/auth/signup',headers={'Origin':'https://testserver'},json={**body,'termsVersion':'old'}).status_code==422
        response=client.post('/api/auth/signup',headers={'Origin':'https://testserver'},json=body)
        assert response.status_code==201 and len(sent)==1
        assert sent[0]['To']=='new@example.test'
        headers={'Origin':'https://testserver','X-CSRF-Token':response.json()['csrfToken']}
        assert client.post('/api/billing/checkout',headers=headers,json={'plan':'starter'}).status_code==428
        import re
        token=re.search(r'#token=([A-Za-z0-9_-]+)',sent[0].get_content()).group(1)
        assert client.post('/api/account/verify-email',headers=headers,json={'token':token}).status_code==200
        assert client.post('/api/billing/checkout',headers=headers,json={'plan':'starter'}).status_code==503 # unconfigured sandbox provider, not an identity gate
        account=client.get('/api/account').json()
        assert account['readiness']['emailVerified'] and account['readiness']['policyAccepted']
        assert client.post('/api/account/verify-email',headers=headers,json={'token':token}).status_code==422

def test_gate_checks_latest_policy_and_works_inside_existing_transaction(tmp_path,monkeypatch):
    monkeypatch.setenv('CLIPBOT_ENFORCE_CUSTOMER_ACCESS','1')
    store=Store(tmp_path/'gate.db');uid=store.create_user('paid@example.test','SafeClipBot!2026','paid_customer')
    access=CustomerAccess(store,'https://testserver',config={'enabled':False})
    with pytest.raises(HTTPException):require_customer_ready(store,uid)
    with store.connection() as db:db.execute('INSERT INTO email_verification VALUES(?,?)',(uid,1))
    access.accept_policy(uid,POLICY_VERSION)
    with store.connection(atomic=True) as db:require_customer_ready(store,uid,db=db)
    with store.connection() as db:db.execute('DELETE FROM legal_acceptances WHERE user_id=?',(uid,))
    with pytest.raises(HTTPException):require_customer_ready(store,uid)

def test_origin_rejection_happens_before_edge_identity_lookups(tmp_path):
    app=create_app(Store(tmp_path/'origin.db'),origin='https://testserver',local_signup=False)
    with TestClient(app,base_url='https://testserver') as client:
        assert client.post('/api/billing/change',headers={'Origin':'https://hostile.example'},json={'plan':'creator'}).status_code==403
        assert app.state.edge_guard.active==0
