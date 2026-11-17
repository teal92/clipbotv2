import pytest
from test_companion import setup
from test_companion_release_catalog import write_release
from fastapi.testclient import TestClient
from server.app import create_app


def payload(target=None, version='0.2.10'):
    result = {'ready': True, 'monitoring': False, 'acknowledgedRevision': '', 'hardwareSlots': 2, 'activeScouts': 0, 'errorCode': None, 'version': version}
    if target is not None:
        result['platformTarget'] = target
    return result


def test_legacy_windows_and_native_reports_keep_separate_versions(setup):
    store, uid, token, scouts, companion = setup
    companion.required_versions = lambda target: '0.3.0' if target.startswith('macos-') else '0.2.10'
    companion.report(token, payload())
    assert companion.status(uid)['platformTarget'] == 'windows-x86_64'
    assert companion.status(uid)['requiredVersion'] == '0.2.10'
    with pytest.raises(ValueError):
        companion.report(token, payload('macos-arm64', '0.3.0'))
    with pytest.raises(ValueError):
        companion.report(token, payload('linux-arm64'))


def test_owner_native_download_selects_only_allowlisted_artifact(setup, monkeypatch):
    store, uid, token, scouts, companion = setup
    write_release(store.path.parent, 'macos-arm64', '0.3.0')
    monkeypatch.setenv('CLIPBOT_ADMIN_USER_ID', uid)
    session, _ = store.new_session(uid)
    with TestClient(create_app(store, origin='http://testserver')) as client:
        assert client.get('/api/companion/download?target=macos-arm64').status_code == 401
        client.cookies.set('clipbot_session', session)
        response = client.get('/api/companion/download?target=macos-arm64')
        assert response.status_code == 200
        assert response.content == b'native-package'
        assert 'ClipBotCompanion-arm64.dmg' in response.headers['content-disposition']
        assert client.get('/api/companion/download?target=../../private').status_code == 422
        assert client.get('/api/companion/download?target=macos-x86_64').status_code == 503
        assert client.get('/api/companion/status?target=macos-arm64').json()['download']['target'] == 'macos-arm64'


def test_repair_heartbeat_retains_native_platform(monkeypatch):
    from worker.lifecycle import CompanionHealth
    reports = []
    class Client:
        token = 'paired'
        def companion_heartbeat(self, data):
            reports.append(data)
    monkeypatch.setattr('worker.platforms.identity.current_target', lambda: 'macos-arm64')
    assert CompanionHealth(Client(), 2).tick() == 5
    assert reports[0].get('platformTarget') == 'macos-arm64'
