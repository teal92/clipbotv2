import hashlib
import importlib
import json
import sys
import struct

import pytest


def native_inputs(tmp_path):
    target = 'macos-arm64'
    files = {
        f'packaging/tools/native/{target}/bin/ffmpeg': b'media',
        f'packaging/tools/native/{target}/bin/ffprobe': b'probe',
        f'packaging/tools/native/{target}/bin/yt-dlp': b'downloader',
        f'packaging/tools/native/{target}/wheels/av-reviewed.whl': b'reviewed-wheel',
        f'packaging/native/{target}/corresponding-source.zip': b'source-fixture',
        f'packaging/platforms/{target}.lock': b'reviewed-lock',
        f'packaging/platforms/{target}.approved.json': b'{}',
        f'packaging/native/{target}/THIRD-PARTY-NOTICES.txt': b'notices',
        'worker/data/models/base/model.bin': b'model',
        'worker/data/models/base/config.json': b'config',
        'worker/data/models/base/tokenizer.json': b'tokenizer',
        'worker/data/models/base/vocabulary.txt': b'vocabulary',
    }
    artifacts = []
    for name, data in files.items():
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        role = 'compiler' if name.endswith('.whl') else 'source' if name.endswith('.zip') else 'notice' if name.endswith('.txt') and 'NOTICES' in name else 'lock' if 'platforms/' in name else 'model' if 'models/' in name else 'media'
        artifacts.append({'path': name, 'role': role, 'sha256': hashlib.sha256(data).hexdigest(), 'sizeBytes': len(data)})
    return {'schemaVersion': 1, 'target': target, 'releaseVersion': '0.3.0-beta.1', 'minimumOS': '14.0', 'sourceComplete': True, 'dependencyLockComplete': True, 'artifacts': artifacts}


def test_native_inputs_reject_wrong_architecture_before_reading_files(tmp_path):
    verifier = importlib.import_module('tools.verify_native_release_inputs')
    with pytest.raises(ValueError, match='host'):
        verifier.verify_native_inputs(tmp_path, native_inputs(tmp_path), 'macos-arm64', host_target='windows-x86_64')


def test_native_inputs_pin_every_tool_model_lock_source_and_notice(tmp_path):
    verifier = importlib.import_module('tools.verify_native_release_inputs')
    data = native_inputs(tmp_path)
    assert verifier.verify_native_inputs(tmp_path, data, 'macos-arm64', host_target='macos-arm64') == 12
    (tmp_path / 'packaging/tools/native/macos-arm64/bin/ffmpeg').write_bytes(b'altered')
    with pytest.raises(ValueError, match='changed|hash'):
        verifier.verify_native_inputs(tmp_path, data, 'macos-arm64', host_target='macos-arm64')


@pytest.mark.parametrize('missing', ['sourceComplete', 'dependencyLockComplete'])
def test_native_inputs_never_accept_incomplete_review(tmp_path, missing):
    verifier = importlib.import_module('tools.verify_native_release_inputs')
    data = native_inputs(tmp_path)
    data[missing] = False
    with pytest.raises(ValueError, match='incomplete'):
        verifier.verify_native_inputs(tmp_path, data, 'macos-arm64', host_target='macos-arm64')


def test_native_input_inventory_cannot_omit_corresponding_sources(tmp_path):
    verifier = importlib.import_module('tools.verify_native_release_inputs')
    data = native_inputs(tmp_path)
    data['artifacts'] = [item for item in data['artifacts'] if item['role'] != 'source']
    with pytest.raises(ValueError, match='inventory'):
        verifier.verify_native_inputs(tmp_path, data, 'macos-arm64', host_target='macos-arm64')


def test_native_inputs_require_a_reviewed_decoder_wheel(tmp_path):
    verifier = importlib.import_module('tools.verify_native_release_inputs')
    data = native_inputs(tmp_path)
    data['artifacts'] = [item for item in data['artifacts'] if not item['path'].endswith('.whl')]
    with pytest.raises(ValueError, match='wheel'):
        verifier.verify_native_inputs(tmp_path,data,'macos-arm64',host_target='macos-arm64')


def test_native_installed_pyav_must_match_reviewed_wheel_bytes(tmp_path):
    import zipfile
    verifier = importlib.import_module('tools.verify_native_release_inputs')
    wheel = tmp_path/'av-reviewed.whl'
    site = tmp_path/'site'
    payload = {'av/__init__.py':b'','av/_core.abi3.so':b'compiled bindings',
               'av/.dylibs/libavcodec.62.dylib':b'controlled decoder'}
    with zipfile.ZipFile(wheel,'w') as archive:
        for name,data in payload.items():
            archive.writestr(name,data)
            path = site/name
            path.parent.mkdir(parents=True,exist_ok=True)
            path.write_bytes(data)
    assert verifier.verify_native_pyav(wheel,site) == 3
    (site/'av/_core.abi3.so').write_bytes(b'other vendor build')
    with pytest.raises(ValueError,match='differs'):
        verifier.verify_native_pyav(wheel,site)


def test_native_pyav_review_rejects_unsafe_wheel_members(tmp_path):
    import zipfile
    verifier = importlib.import_module('tools.verify_native_release_inputs')
    wheel = tmp_path/'av-reviewed.whl'
    with zipfile.ZipFile(wheel,'w') as archive:
        archive.writestr('../outside',b'unsafe')
    with pytest.raises(ValueError,match='Unsafe'):
        verifier.verify_native_pyav(wheel,tmp_path/'site')


def test_native_approved_versions_cannot_invent_packages_or_silently_downgrade():
    from pathlib import Path
    verifier = importlib.import_module('tools.verify_native_release_inputs')
    records = json.loads(Path('packaging/platforms/macos-arm64.dependencies.json').read_text())['packages']
    approved = {item['name']:item['version'] for item in records}
    assert verifier.verify_native_approved(approved,'macos-arm64') is None
    with pytest.raises(ValueError,match='committed'):
        verifier.verify_native_approved({**approved,'invented-native-package':'1.0'},'macos-arm64')
    with pytest.raises(ValueError,match='committed'):
        verifier.verify_native_approved({**approved,'av':'17.0.0'},'macos-arm64')


def test_candidate_builder_keeps_source_clean_and_stages_inputs_separately(tmp_path, monkeypatch):
    import importlib.util
    from pathlib import Path
    from types import SimpleNamespace
    spec = importlib.util.spec_from_file_location('native_builder_under_test',Path('packaging/build-native.py'))
    builder = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(builder)
    monkeypatch.setattr(builder,'current_target',lambda:'macos-arm64')
    monkeypatch.setattr(builder,'run',lambda args,**kwargs:SimpleNamespace(stdout='a'*40 if args[1]=='rev-parse' else ''))
    assets = tmp_path/'assets'
    manifest = assets/'packaging/platforms/macos-arm64.inputs.json'
    manifest.parent.mkdir(parents=True)
    manifest.write_text('{}')
    roots=[]
    def gate(root,*args):
        roots.append(root)
        raise ValueError('Stop before compiling')
    monkeypatch.setattr(builder,'verify_native_environment',gate)
    with pytest.raises(ValueError,match='Stop before'):
        builder.build('macos-arm64',tmp_path/'dist',inputs_root=assets)
    assert roots == [assets]
    assert not (tmp_path/'dist').exists()


def test_candidate_builder_rejects_dirty_source_even_with_external_inputs(tmp_path, monkeypatch):
    import importlib.util
    from pathlib import Path
    from types import SimpleNamespace
    spec = importlib.util.spec_from_file_location('dirty_native_builder',Path('packaging/build-native.py'))
    builder = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(builder)
    monkeypatch.setattr(builder,'current_target',lambda:'macos-arm64')
    monkeypatch.setattr(builder,'run',lambda args,**kwargs:SimpleNamespace(stdout='a'*40 if args[1]=='rev-parse' else ' M worker/capture.py'))
    with pytest.raises(ValueError,match='clean committed'):
        builder.build('macos-arm64',tmp_path/'dist',inputs_root=tmp_path/'assets')
    assert not (tmp_path/'dist').exists()


def test_native_binary_architecture_rejects_windows_payload():
    verifier = importlib.import_module('tools.verify_native_release_inputs')
    with pytest.raises(ValueError):
        verifier.binary_architectures(b'MZ' + b'\x00' * 60)
    elf = bytearray(64)
    elf[:6] = b'\x7fELF\x02\x01'
    elf[18:20] = (62).to_bytes(2, 'little')
    assert verifier.binary_architectures(bytes(elf)) == {'linux-x86_64'}


def test_native_builder_refuses_wrong_host_without_creating_output(tmp_path):
    import subprocess
    target='linux-x86_64' if sys.platform=='darwin' else 'macos-arm64'
    result = subprocess.run([sys.executable, 'packaging/build-native.py', '--target', target, '--output', str(tmp_path / 'dist')], capture_output=True, text=True)
    assert result.returncode != 0
    assert 'native host' in result.stdout
    assert not (tmp_path / 'dist').exists()


def test_packaged_native_version_is_bound_to_its_target(tmp_path, monkeypatch):
    version = importlib.import_module('worker.version')
    monkeypatch.setattr('worker.platforms.identity.current_target', lambda: 'macos-arm64')
    path = tmp_path / 'native-release.json'
    path.write_text(json.dumps({'version':'0.3.0-beta.1','target':'macos-arm64'}))
    assert version.version_for_bundle(tmp_path) == '0.3.0-beta.1'
    path.write_text(json.dumps({'version':'0.3.0-beta.1','target':'macos-x86_64'}))
    with pytest.raises(RuntimeError):
        version.version_for_bundle(tmp_path)


def test_native_audit_still_rejects_customer_files(tmp_path):
    from packaging_audit import audit_bundle
    (tmp_path / 'device.bin').write_bytes(b'private')
    assert any('Forbidden' in error for error in audit_bundle(tmp_path, allow_internal_links=True))


def test_lgpl_tray_library_is_supplied_as_replaceable_source():
    import ast
    from pathlib import Path
    tree=ast.parse(Path('packaging/native-companion.spec').read_text())
    analysis=next(node for node in ast.walk(tree) if isinstance(node,ast.Call)
                  and isinstance(node.func,ast.Name) and node.func.id=='Analysis')
    mode=next((ast.literal_eval(kw.value) for kw in analysis.keywords if kw.arg=='module_collection_mode'),{})
    assert mode.get('pystray')=='py'


def test_macos_binary_cannot_require_newer_os_than_advertised():
    verifier = importlib.import_module('tools.verify_native_release_inputs')
    header = struct.pack('<8I',0xfeedfacf,0x0100000c,0,2,1,24,0,0)
    command = struct.pack('<6I',0x32,24,1,15<<16,15<<16,0)
    with pytest.raises(ValueError, match='minimum OS'):
        verifier.verify_binary_target(header+command,'macos-arm64','14.0')
    assert verifier.verify_binary_target(header+command,'macos-arm64','15.0') is None
    with pytest.raises(ValueError):
        verifier.verify_binary_target(header+command,'macos-x86_64','15.0')


@pytest.mark.skipif(sys.platform == 'win32', reason='native POSIX package links')
def test_bundle_audit_permits_only_internal_native_framework_links(tmp_path):
    from packaging_audit import audit_bundle
    (tmp_path / 'real').mkdir()
    (tmp_path / 'real/lib.so').write_bytes(b'library')
    (tmp_path / 'framework-link').symlink_to(tmp_path / 'real', target_is_directory=True)
    assert audit_bundle(tmp_path, allow_internal_links=True) == []
    assert audit_bundle(tmp_path)
    (tmp_path / 'outside').symlink_to(tmp_path.parent, target_is_directory=True)
    assert audit_bundle(tmp_path, allow_internal_links=True)
