import hashlib,json
from fastapi.testclient import TestClient
from server.store import Store
from server.app import create_app


def setup(tmp_path,monkeypatch,enabled,production):
    monkeypatch.setenv('CLIPBOT_COMPANION_PUBLIC_RELEASE','1' if enabled else '0')
    store=Store(tmp_path/'site.db');uid=store.create_user('release@example.test','SafePassword!2026','release')
    token,csrf=store.new_session(uid)
    folder=tmp_path/'companion';folder.mkdir();blob=b'non-executable test fixture'
    (folder/'ClipBotCompanionSetup.exe').write_bytes(blob)
    manifest={'version':'0.2.8','sha256':hashlib.sha256(blob).hexdigest(),'sizeBytes':len(blob),'signed':production,'channel':'production' if production else 'internal','provenanceVerified':production,'cleanMachineAccepted':production}
    (folder/'manifest.json').write_text(json.dumps(manifest))
    app=create_app(store,origin='http://testserver')
    if production:
        from server.legal import POLICY_VERSION
        app.state.customer_access.accept_policy(uid,POLICY_VERSION)
        with store.connection() as db:db.execute('INSERT INTO email_verification VALUES(?,?)',(uid,1))
    return app,token


def test_customer_download_remains_off_until_release_switch(tmp_path,monkeypatch):
    app,token=setup(tmp_path,monkeypatch,False,True)
    with TestClient(app) as client:
        client.cookies.set('clipbot_session',token)
        assert client.get('/api/companion/download').status_code==403


def test_unsigned_or_unaccepted_installer_is_not_a_customer_release(tmp_path,monkeypatch):
    app,token=setup(tmp_path,monkeypatch,True,False)
    with TestClient(app) as client:
        client.cookies.set('clipbot_session',token)
        assert client.get('/api/companion/download').status_code==503


def test_verified_release_is_account_scoped_and_requires_matching_worker_version(tmp_path,monkeypatch):
    app,token=setup(tmp_path,monkeypatch,True,True)
    with TestClient(app) as client:
        assert client.get('/api/companion/download').status_code==401
        client.cookies.set('clipbot_session',token)
        status=client.get('/api/companion/status').json()
        assert status['requiredVersion']=='0.2.8' and status['download']['version']=='0.2.8'
        response=client.get('/api/companion/download')
        assert response.status_code==200 and response.content==b'non-executable test fixture'
        assert 'no-store' in response.headers['cache-control']


def test_customer_installer_requires_email_verification_even_with_release_enabled(tmp_path,monkeypatch):
    app,token=setup(tmp_path,monkeypatch,True,True)
    with app.state.store.connection() as db:db.execute('DELETE FROM email_verification')
    with TestClient(app) as client:
        client.cookies.set('clipbot_session',token)
        assert client.get('/api/companion/download').status_code==428


def test_legacy_external_url_cannot_bypass_release_gate_in_status_or_workspace(tmp_path,monkeypatch):
    monkeypatch.setenv('CLIPBOT_COMPANION_DOWNLOAD_URL','https://external.example/setup.exe')
    monkeypatch.setenv('CLIPBOT_COMPANION_VERSION','0.2.8')
    monkeypatch.setenv('CLIPBOT_COMPANION_SHA256','a'*64)
    app,token=setup(tmp_path,monkeypatch,False,True)
    with TestClient(app) as client:
        client.cookies.set('clipbot_session',token)
        assert client.get('/api/companion/status').json()['download']=={'available':False}
        assert client.get('/api/workspace').json()['scouts']['companion']['download']=={'available':False}


def test_internal_owner_installer_sets_matching_version_without_customer_release(tmp_path,monkeypatch):
    app,token=setup(tmp_path,monkeypatch,False,False)
    assert app.state.companion.required_version=='0.2.8'
