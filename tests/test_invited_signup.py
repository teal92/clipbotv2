import hashlib
import re
import pytest
from fastapi.testclient import TestClient
from server.app import create_app
from server.store import Store
from server.legal import POLICY_VERSION
from server.customer_access import require_customer_ready
from fastapi import HTTPException

EMAIL='invited@example.test'
DIGEST=hashlib.sha256(EMAIL.encode()).hexdigest()

def setup(tmp_path,monkeypatch,restriction=DIGEST,public='0'):
    monkeypatch.setenv('CLIPBOT_SIGNUP_EMAIL_HASHES',restriction)
    monkeypatch.setenv('CLIPBOT_PUBLIC_SIGNUP',public)
    monkeypatch.delenv('CLIPBOT_ENFORCE_CUSTOMER_ACCESS',raising=False)
    store=Store(tmp_path/'invited.db')
    app=create_app(store,origin='https://testserver',local_signup=False)
    access=app.state.customer_access;sent=[]
    access.config={'enabled':True,'sender':'support@example.test'}
    access.edge_verified=True;access.transport=sent.append
    return app,store,sent

def signup(client,email=EMAIL,**overrides):
    return client.post('/api/auth/signup',headers={'Origin':'https://testserver'},json={
        'email':email,'name':'invited_customer','password':'SafeClipBot!2026','termsVersion':POLICY_VERSION,**overrides})

def test_invitation_allows_only_normalized_address_and_requires_real_verification(tmp_path,monkeypatch):
    app,store,sent=setup(tmp_path,monkeypatch)
    with TestClient(app,base_url='https://testserver') as client:
        assert signup(client,'other@example.test').status_code==503
        response=signup(client,'  INVITED@EXAMPLE.TEST ')
        assert response.status_code==201
        assert len(sent)==1 and sent[0]['To']==EMAIL
        account=client.get('/api/account').json()
        assert account['readiness']['enforced'] and not account['readiness']['emailVerified']
        with store.connection() as db:uid=db.execute('SELECT id FROM users').fetchone()[0]
        with pytest.raises(HTTPException):require_customer_ready(store,uid)
        headers={'Origin':'https://testserver','X-CSRF-Token':response.json()['csrfToken']}
        assert client.post('/api/billing/checkout',headers=headers,json={'plan':'starter'}).status_code==428
        token=re.search(r'#token=([A-Za-z0-9_-]+)',sent[0].get_content()).group(1)
        assert client.post('/api/account/verify-email',headers=headers,json={'token':token}).status_code==200
        # No companion is paired: identity is ready and only the absent test
        # provider prevents checkout, rather than a companion requirement.
        assert client.post('/api/billing/checkout',headers=headers,json={'plan':'starter'}).status_code==503
        assert client.get('/api/account').json()['readiness']['ready']

@pytest.mark.parametrize('restriction',['','bad',DIGEST+',',DIGEST.upper(),','.join([DIGEST]*21),'x'*10000])
def test_malformed_invitation_configuration_cannot_open_public_signup(tmp_path,monkeypatch,restriction):
    app,store,sent=setup(tmp_path,monkeypatch,restriction,public='1')
    with TestClient(app,base_url='https://testserver') as client:assert signup(client).status_code==503
    with store.connection() as db:assert db.execute('SELECT COUNT(*) FROM users').fetchone()[0]==0
    assert not sent

@pytest.mark.parametrize('failure',['mail','edge','password','policy'])
def test_invitation_never_bypasses_existing_signup_protections(tmp_path,monkeypatch,failure):
    app,store,sent=setup(tmp_path,monkeypatch)
    changes={}
    if failure=='mail':app.state.customer_access.config={'enabled':False}
    if failure=='edge':app.state.customer_access.edge_verified=False
    if failure=='password':changes={'password':'weak'}
    if failure=='policy':changes={'termsVersion':'old'}
    with TestClient(app,base_url='https://testserver') as client:
        assert signup(client,**changes).status_code==(503 if failure in ('mail','edge') else 422)
    with store.connection() as db:assert db.execute('SELECT COUNT(*) FROM users').fetchone()[0]==0
    assert not sent
