import zipfile
import pytest


def fixture(tmp_path):
    wheel = tmp_path / 'av.whl'
    files = {'av/__init__.py': b'# verified loader', 'av/_core.pyd': b'compiled source',
             'av.libs/avcodec-local.dll': b'local ffmpeg'}
    with zipfile.ZipFile(wheel, 'w') as archive:
        for name, data in files.items():
            archive.writestr(name, data)
    site = tmp_path / 'site'
    for name, data in files.items():
        path = site / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    return wheel, site


def test_same_package_version_cannot_substitute_old_native_wheel(tmp_path):
    from tools.verify_release_inputs import verify_installed_native_wheel
    wheel, site = fixture(tmp_path)
    assert verify_installed_native_wheel(wheel, site) == 3
    (site / 'av.libs/avcodec-local.dll').write_bytes(b'old vendor build')
    with pytest.raises(ValueError, match='differs'):
        verify_installed_native_wheel(wheel, site)


def test_unlisted_native_modules_and_loader_changes_fail(tmp_path):
    from tools.verify_release_inputs import verify_installed_native_wheel
    wheel, site = fixture(tmp_path)
    (site / 'av.libs/unreviewed.dll').write_bytes(b'extra runtime')
    with pytest.raises(ValueError, match='Unlisted'):
        verify_installed_native_wheel(wheel, site)
    (site / 'av.libs/unreviewed.dll').unlink()
    (site / 'av/__init__.py').write_bytes(b'import untrusted')
    with pytest.raises(ValueError, match='differs'):
        verify_installed_native_wheel(wheel, site)


@pytest.mark.parametrize('name', ['av/../../outside.dll', 'av/_core.pyd/../escape.dll'])
def test_native_wheel_paths_cannot_escape_installation(tmp_path, name):
    from tools.verify_release_inputs import verify_installed_native_wheel
    wheel, site = fixture(tmp_path)
    with zipfile.ZipFile(wheel, 'a') as archive:
        archive.writestr(name, b'unsafe')
    with pytest.raises(ValueError):
        verify_installed_native_wheel(wheel, site)


def test_missing_binary_payload_and_duplicate_members_fail(tmp_path):
    from tools.verify_release_inputs import verify_installed_native_wheel
    wheel, site = fixture(tmp_path)
    with zipfile.ZipFile(wheel, 'a') as archive:
        with pytest.warns(UserWarning,match='Duplicate'):
            archive.writestr('av/_core.pyd', b'other')
    with pytest.raises(ValueError):
        verify_installed_native_wheel(wheel, site)
    with zipfile.ZipFile(wheel, 'w') as archive:
        archive.writestr('av/__init__.py', b'# verified loader')
    with pytest.raises(ValueError):
        verify_installed_native_wheel(wheel, site)
