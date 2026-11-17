import importlib
import io
import tarfile
from pathlib import Path

import pytest


def module():
    return importlib.import_module('tools.build_native_runtime')


def archive(path, name='source/configure', kind=None):
    with tarfile.open(path, 'w:gz') as output:
        entry = tarfile.TarInfo(name)
        if kind:
            entry.type = kind
            entry.linkname = '../../outside'
            output.addfile(entry)
        else:
            entry.size = 4
            entry.mode = 0o7777
            output.addfile(entry, io.BytesIO(b'test'))


def test_bootstrap_accepts_only_reviewed_sources_and_matching_host(tmp_path):
    bootstrap = module()
    pins = bootstrap.read_pins()
    assert pins['python']['version'] == '3.12.15'
    assert set(pins) == {'python', 'openssl', 'libffi'}
    for record in pins.values():
        assert len(record['sha256']) == 64
        assert record['url'].startswith('https://')
    with pytest.raises(ValueError, match='matching native'):
        bootstrap.build('macos-arm64', tmp_path/'out', host_target='windows-x86_64')
    assert not (tmp_path/'out').exists()


@pytest.mark.parametrize('name,kind', [('../escape', None), ('/absolute', None), ('source/link', tarfile.SYMTYPE), ('source/link', tarfile.LNKTYPE), ('source/device', tarfile.CHRTYPE), ('source\\escape', None)])
def test_source_extraction_rejects_escape_links_and_special_files(tmp_path, name, kind):
    path = tmp_path/'source.tar.gz'
    archive(path, name, kind)
    with pytest.raises(ValueError):
        module().extract_source(path, tmp_path/'destination')
    assert not (tmp_path/'outside').exists()


def test_source_extraction_strips_privileged_permissions(tmp_path):
    path = tmp_path/'source.tar.gz'
    archive(path)
    result = module().extract_source(path, tmp_path/'destination')
    assert result == tmp_path/'destination/source'
    assert (result/'configure').read_bytes() == b'test'
    if __import__('os').name != 'nt':
        assert (result/'configure').stat().st_mode & 0o7777 == 0o755


def test_source_extraction_rejects_duplicate_and_oversized_members(tmp_path):
    path = tmp_path/'duplicate.tar'
    with tarfile.open(path, 'w') as output:
        for _ in range(2):
            entry = tarfile.TarInfo('source/file')
            output.addfile(entry, io.BytesIO())
    with pytest.raises(ValueError, match='Duplicate'):
        module().extract_source(path, tmp_path/'destination')
    path = tmp_path/'big.tar'
    with tarfile.open(path, 'w') as output:
        entry = tarfile.TarInfo('source/large')
        entry.size = 200_000_001
        # A deliberately truncated archive must fail before attempting its payload.
        output.fileobj.write(entry.tobuf())
    with pytest.raises(ValueError, match='limit'):
        module().extract_source(path, tmp_path/'large')


def test_changed_source_archive_is_rejected(tmp_path):
    path = tmp_path/'source.tar'
    path.write_bytes(b'altered')
    with pytest.raises(ValueError, match='hash'):
        module().verify_source(path, {'sha256':'0'*64,'sizeBytes':7})


def test_source_download_never_deletes_existing_input(tmp_path):
    path = tmp_path/'source.tar'
    path.write_bytes(b'keep reviewed input')
    with pytest.raises(ValueError, match='exists'):
        module().download(module().read_pins()['python'], path)
    assert path.read_bytes() == b'keep reviewed input'


def test_build_runtime_copies_valid_roots_into_its_own_prefix_only(tmp_path):
    import certifi
    import hashlib
    import ssl
    source = Path(certifi.where())
    prefix = tmp_path/'dependencies'
    receipt = module().install_build_ca_bundle(prefix,candidates=[source])
    destination = prefix/'ssl/cert.pem'
    assert destination.read_bytes() == source.read_bytes()
    assert receipt['sha256'] == hashlib.sha256(source.read_bytes()).hexdigest()
    context = ssl.create_default_context(cafile=destination)
    assert context.verify_mode == ssl.CERT_REQUIRED and context.check_hostname is True
    assert context.cert_store_stats()['x509_ca'] > 0


def test_build_runtime_does_not_accept_invalid_roots_or_disable_tls(tmp_path):
    source = tmp_path/'invalid.pem'
    source.write_text('not a certificate')
    with pytest.raises(ValueError,match='certificate'):
        module().install_build_ca_bundle(tmp_path/'dependencies',candidates=[source])
    assert not (tmp_path/'dependencies/ssl/cert.pem').exists()


def test_native_build_runtime_pin_does_not_change_windows():
    import json
    from tools.verify_native_release_inputs import verify_native_runtime
    for name in ('macos', 'linux'):
        assert json.loads(Path(f'packaging/platforms/{name}.json').read_text())['python'] == '3.12.15'
    assert verify_native_runtime(('cpython', (3, 12, 15), 64)) is None
    with pytest.raises(ValueError):
        verify_native_runtime(('cpython', (3, 12, 14), 64))
    from tools.verify_release_inputs import verify_build_runtime
    assert verify_build_runtime({'implementation':'cpython','version':(3,12,14),'platform':'win32','bits':64,'buildPlatform':'win-amd64'}) is None
