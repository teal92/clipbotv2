from fastapi.testclient import TestClient
from server.app import create_app
from server.store import Store

def test_connection_preflight_is_authenticated_and_never_claims_oauth_ready(tmp_path,monkeypatch):
    monkeypatch.setenv('TWITCH_CLIENT_SECRET','DO-NOT-EXPOSE')
    store=Store(tmp_path/'connections.db')
    store.create_user('one@example.com','a-good-long-password','One')
    with TestClient(create_app(store,origin='http://testserver')) as c:
        assert c.get('/api/connections').status_code==401
        account=c.post('/api/auth/login',json={'email':'one@example.com','password':'a-good-long-password'},headers={'Origin':'http://testserver'}).json()
        response=c.get('/api/connections')
        assert response.status_code==200
        assert len(response.json()['platforms'])==5
        assert all(not p['connected'] and not p['authorizationAvailable'] for p in response.json()['platforms'])
        assert 'DO-NOT-EXPOSE' not in response.text
        headers={'Origin':'http://testserver','X-CSRF-Token':account['csrfToken']}
        assert c.post('/api/connections/twitch/start',json={'accountType':'personal'},headers={'Origin':'http://testserver'}).status_code==403
        assert c.post('/api/connections/twitch/start',json={'accountType':'developer'},headers=headers).status_code==503
        assert c.post('/api/connections/unknown/start',json={'accountType':'personal'},headers=headers).status_code==404
        assert c.post('/api/connections/twitch/start',json={'accountType':'admin'},headers=headers).status_code==422
