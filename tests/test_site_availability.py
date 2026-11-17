from fastapi.testclient import TestClient
from server.app import create_app
from server.store import Store


def test_owner_control_is_authenticated_revision_checked_and_persistent(tmp_path,monkeypatch):
    monkeypatch.setenv('CLIPBOT_C2_SERVICE_KEY','s'*40)
    store=Store(tmp_path/'site.db')
    app=create_app(store,origin='http://testserver')
    with TestClient(app) as client:
        assert client.get('/api/operator/availability').status_code==401
        assert client.post('/api/operator/availability',headers={'Origin':'http://testserver'},json={'online':False,'expectedRevision':0,'confirmed':True}).status_code==401
        headers={'Origin':'http://testserver','Authorization':'Bearer '+'s'*40}
        initial=client.get('/api/operator/availability',headers=headers)
        assert initial.status_code==200
        before=initial.json();assert before['online'] is True and before['audience']=='private preview'
        body={'online':False,'expectedRevision':before['revision'],'confirmed':True}
        assert client.post('/api/operator/availability',headers={**headers,'Origin':'https://evil.example'},json=body).status_code==403
        for patch in ({'online':'false'},{'confirmed':False},{'expectedRevision':True},{'command':'arbitrary'}):
            assert client.post('/api/operator/availability',headers=headers,json={**body,**patch}).status_code in (400,422)
        closed=client.post('/api/operator/availability',headers=headers,json=body)
        assert closed.status_code==200 and closed.json()['online'] is False
        assert client.get('/').status_code==503
        assert 'temporarily offline' in client.get('/').text
        assert client.get('/api/auth/options').status_code==503
        assert client.get('/healthz').status_code==200
        assert client.get('/api/worker/config').status_code==401
        assert client.post('/api/worker/pairing',headers={'Origin':'http://testserver'}).status_code==503
        assert client.post('/api/worker/connect',headers={'Origin':'http://testserver'},json={'code':'x'*32}).status_code==503
        assert client.post('/api/billing/webhook',json={}).status_code==400
        assert client.post('/api/operator/availability',headers=headers,json=body).status_code==409
    with TestClient(create_app(Store(tmp_path/'site.db'),origin='http://testserver')) as client:
        assert client.get('/').status_code==503
        state=client.get('/api/operator/availability',headers=headers).json()
        opened=client.post('/api/operator/availability',headers=headers,json={'online':True,'expectedRevision':state['revision'],'confirmed':True})
        assert opened.status_code==200 and opened.json()['online'] is True
        assert opened.json()['audience']=='private preview'
        assert client.get('/').status_code==200
        # Reopening never enables signup, AI, or an unsigned public installer.
        assert not app.state.customer_access.public_signup
