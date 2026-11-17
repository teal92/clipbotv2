import hashlib
import importlib
import io
import tarfile

import pytest


def module():
    return importlib.import_module('tools.native_source_bundle')


def test_runtime_sources_require_actual_pinned_archives(tmp_path,monkeypatch):
    source = tmp_path/'sources/Python.tar.xz'
    source.parent.mkdir()
    source.write_bytes(b'reviewed runtime source')
    pin = {'url':'https://www.python.org/Python.tar.xz','sizeBytes':source.stat().st_size,
           'sha256':hashlib.sha256(source.read_bytes()).hexdigest()}
    monkeypatch.setattr(module(),'read_runtime_pins',lambda:{'python':pin})
    assert module().runtime_sources(tmp_path)['runtime/sources/Python.tar.xz'] == source
    source.write_bytes(b'changed')
    with pytest.raises(ValueError):
        module().runtime_sources(tmp_path)


def test_matching_source_uses_strong_checksums_not_similar_filenames(tmp_path):
    source = tmp_path/'ffmpeg.tar.gz'
    source.write_bytes(b'matching source')
    digest = hashlib.sha512(source.read_bytes()).hexdigest()
    index = module().archive_index(tmp_path)
    records = [{'SPDXID':'SPDXRef-resource-0','name':'ffmpeg/ffmpeg','downloadLocation':'git+https://github.com/ffmpeg/ffmpeg@n8.1.2',
                'checksums':[{'algorithm':'SHA512','checksumValue':digest}]}]
    assert module().matching_resources(records,index)[0][1] == source
    records[0]['checksums'][0]['checksumValue'] = '0'*128
    with pytest.raises(ValueError,match='Matching source'):
        module().matching_resources(records,index)


def test_native_sources_reject_weak_or_missing_resource_checksums(tmp_path):
    source = tmp_path/'source.zip'
    source.write_bytes(b'source')
    for checksums in ([],[{'algorithm':'MD5','checksumValue':'a'*32}]):
        with pytest.raises(ValueError):
            module().matching_resources([{'SPDXID':'SPDXRef-resource-0','checksums':checksums}],module().archive_index(tmp_path))


def test_source_recipe_tar_rejects_escape_and_links():
    for name,kind in [('../outside',tarfile.REGTYPE),('link',tarfile.SYMTYPE)]:
        stream = io.BytesIO()
        with tarfile.open(fileobj=stream,mode='w') as output:
            entry = tarfile.TarInfo(name)
            entry.type = kind
            output.addfile(entry)
        with pytest.raises(ValueError):
            module().validate_recipe_tar(stream.getvalue())


def test_missing_native_source_evidence_cannot_become_a_complete_bundle(tmp_path):
    with pytest.raises(ValueError):
        module().build_bundle(tmp_path/'media',tmp_path/'pyav',tmp_path/'sources.zip','macos-arm64')
    assert not (tmp_path/'sources.zip').exists()
