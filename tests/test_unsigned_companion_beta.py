import json
import pytest
from fastapi.testclient import TestClient
from server.app import create_app
from server.legal import POLICY_VERSION
from test_public_companion_release import setup


def beta(tmp_path,monkeypatch,enabled=True):
    monkeypatch.setenv('CLIPBOT_COMPANION_UNSIGNED_BETA','1' if enabled else '0')
    app,token=setup(tmp_path,monkeypatch,True,False)
    path=tmp_path/'companion'/'manifest.json';manifest=json.loads(path.read_text())
    manifest.update(channel='beta',provenanceVerified=True,cleanInstallPairedAccepted=True)
    path.write_text(json.dumps(manifest))
    store=app.state.store;session=store.session(token);uid=session['user_id']
    app=create_app(store,origin='http://testserver');app.state.customer_access.accept_policy(uid,POLICY_VERSION)
    with store.connection() as db:db.execute('INSERT INTO email_verification VALUES(?,?)',(uid,1))
    return app,token,session['csrf'],manifest


def test_unsigned_beta_requires_explicit_release_policy_and_per_artifact_acknowledgment(tmp_path,monkeypatch):
    app,token,csrf,manifest=beta(tmp_path,monkeypatch)
    with TestClient(app) as client:
        client.cookies.set('clipbot_session',token)
        status=client.get('/api/companion/status').json()['download']
        assert status['signed'] is False and status['unsignedBeta'] is True and status['requiresBetaAcceptance'] is True
        assert client.get('/api/companion/download').status_code==428
        payload={'version':manifest['version'],'sha256':manifest['sha256'],'acknowledged':True}
        headers={'Origin':'http://testserver','X-CSRF-Token':csrf}
        assert client.post('/api/companion/beta-accept',headers={'Origin':'http://testserver'},json=payload).status_code==403
        for change in ({'acknowledged':False},{'acknowledged':'true'},{'sha256':'a'*64},{'command':'install'}):
            assert client.post('/api/companion/beta-accept',headers=headers,json={**payload,**change}).status_code in (409,422)
        assert client.post('/api/companion/beta-accept',headers=headers,json=payload).status_code==200
        assert client.get('/api/companion/download').status_code==200
        assert client.get('/api/companion/status').json()['download']['requiresBetaAcceptance'] is False
        other=app.state.store.create_user('other-beta@example.test','SafePassword!2026','otherbeta');other_token,_=app.state.store.new_session(other)
        app.state.customer_access.accept_policy(other,POLICY_VERSION)
        with app.state.store.connection() as db:db.execute('INSERT INTO email_verification VALUES(?,?)',(other,1))
        client.cookies.set('clipbot_session',other_token)
        assert client.get('/api/companion/download').status_code==428


def test_unsigned_beta_is_unavailable_without_its_separate_switch(tmp_path,monkeypatch):
    app,token,csrf,manifest=beta(tmp_path,monkeypatch,False)
    with TestClient(app) as client:
        client.cookies.set('clipbot_session',token)
        assert client.get('/api/companion/download').status_code==503


def test_released_beta_adopts_its_manifest_version(tmp_path,monkeypatch):
    app,token,csrf,manifest=beta(tmp_path,monkeypatch)
    manifest['version']='0.2.9-beta';(tmp_path/'companion'/'manifest.json').write_text(json.dumps(manifest))
    app=create_app(app.state.store,origin='http://testserver')
    assert app.state.companion.required_version=='0.2.9-beta'


def test_beta_consent_cannot_be_recorded_before_verified_account_readiness(tmp_path,monkeypatch):
    app,token,csrf,manifest=beta(tmp_path,monkeypatch)
    with app.state.store.connection() as db:db.execute('DELETE FROM email_verification')
    with TestClient(app) as client:
        client.cookies.set('clipbot_session',token)
        payload={'version':manifest['version'],'sha256':manifest['sha256'],'acknowledged':True}
        assert client.post('/api/companion/beta-accept',headers={'Origin':'http://testserver','X-CSRF-Token':csrf},json=payload).status_code==428


def test_replaced_installer_requires_new_acknowledgment(tmp_path,monkeypatch):
    import hashlib
    app,token,csrf,manifest=beta(tmp_path,monkeypatch)
    with TestClient(app) as client:
        client.cookies.set('clipbot_session',token)
        assert client.post('/api/companion/beta-accept',headers={'Origin':'http://testserver','X-CSRF-Token':csrf},json={'version':manifest['version'],'sha256':manifest['sha256'],'acknowledged':True}).status_code==200
    data=b'replacement nonexecutable fixture';folder=tmp_path/'companion'
    (folder/'ClipBotCompanionSetup.exe').write_bytes(data)
    manifest.update(sha256=hashlib.sha256(data).hexdigest(),sizeBytes=len(data))
    (folder/'manifest.json').write_text(json.dumps(manifest))
    with TestClient(create_app(app.state.store,origin='http://testserver')) as client:
        client.cookies.set('clipbot_session',token)
        assert client.get('/api/companion/download').status_code==428


@pytest.mark.parametrize('change',[{'provenanceVerified':False},{'cleanInstallPairedAccepted':False},{'cleanInstallPairedAccepted':'true'},{'channel':'internal'},{'signed':True}])
def test_beta_never_waives_provenance_or_installed_pairing_acceptance(tmp_path,monkeypatch,change):
    app,token,csrf,manifest=beta(tmp_path,monkeypatch)
    manifest.update(change);(tmp_path/'companion'/'manifest.json').write_text(json.dumps(manifest))
    with TestClient(create_app(app.state.store,origin='http://testserver')) as client:
        client.cookies.set('clipbot_session',token)
        assert client.get('/api/companion/download').status_code==503
