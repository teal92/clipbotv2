import hashlib
import importlib
import json

import pytest


def write_release(root, target, version, blob=b'native-package'):
    filenames = {'windows-x86_64': 'ClipBotCompanionSetup.exe', 'macos-arm64': 'ClipBotCompanion-arm64.dmg', 'macos-x86_64': 'ClipBotCompanion-x86_64.dmg', 'linux-x86_64': 'clipbot-companion-amd64.deb'}
    folder = root / 'companion' if target == 'windows-x86_64' else root / 'companion/targets' / target
    folder.mkdir(parents=True, exist_ok=True)
    (folder / filenames[target]).write_bytes(blob)
    manifest = {'target': target, 'minimumOS': '14.0', 'version': version, 'sha256': hashlib.sha256(blob).hexdigest(), 'sizeBytes': len(blob)}
    (folder / 'manifest.json').write_text(json.dumps(manifest))
    return folder


def test_platform_releases_have_independent_required_versions(tmp_path):
    write_release(tmp_path, 'windows-x86_64', '0.2.10')
    write_release(tmp_path, 'macos-arm64', '0.3.0')
    catalog = importlib.import_module('server.companion_releases').ReleaseCatalog(tmp_path)
    assert catalog.required_version('windows-x86_64') == '0.2.10'
    assert catalog.required_version('macos-arm64') == '0.3.0'
    assert catalog.required_version('macos-x86_64') is None
    assert catalog.installer('macos-arm64').metadata['url'] == '/api/companion/download?target=macos-arm64'
    with pytest.raises(ValueError):
        catalog.installer('../../device.bin')


def test_native_release_cannot_mislabel_architecture(tmp_path):
    folder = write_release(tmp_path, 'macos-arm64', '0.3.0')
    path = folder / 'manifest.json'
    manifest = json.loads(path.read_text())
    manifest['target'] = 'macos-x86_64'
    path.write_text(json.dumps(manifest))
    catalog = importlib.import_module('server.companion_releases').ReleaseCatalog(tmp_path)
    assert catalog.required_version('macos-arm64') is None


def test_native_changed_artifact_fails_closed(tmp_path):
    folder = write_release(tmp_path, 'linux-x86_64', '0.3.0')
    catalog = importlib.import_module('server.companion_releases').ReleaseCatalog(tmp_path)
    installer = catalog.installer('linux-x86_64')
    assert installer.ready()
    (folder / 'clipbot-companion-amd64.deb').write_bytes(b'replaced')
    assert installer.ready() is False
