import importlib
import json
from pathlib import Path

import pytest


def module():
    return importlib.import_module('tools.build_native_media')


def test_native_video_profiles_preserve_tls_subtitles_and_encoding():
    renderer = json.loads(Path('packaging/native/native-renderer/vcpkg.json').read_text())
    features = renderer['dependencies'][0]['features']
    assert {'openssl','version3','ass','x264','ffmpeg','ffprobe'} <= set(features)
    assert renderer['builtin-baseline'] == 'c52f7bd748185ef0e0daf033d9f2ddfc8a3449ea'
    # Windows uses its independent, released configuration.
    windows = json.loads(Path('packaging/native/renderer/vcpkg.json').read_text())
    assert 'openssl' not in windows['dependencies'][0]['features']


def test_native_triplets_bind_architecture_os_floor_and_linkage():
    assert 'VCPKG_TARGET_ARCHITECTURE arm64' in module().triplet('macos-arm64','decoder')
    for target in ('macos-arm64','macos-x86_64'):
        assert 'VCPKG_OSX_DEPLOYMENT_TARGET 14.0' in module().triplet(target,'decoder')
        assert 'VCPKG_LIBRARY_LINKAGE dynamic' in module().triplet(target,'decoder')
        assert 'VCPKG_LIBRARY_LINKAGE static' in module().triplet(target,'renderer')
    assert 'VCPKG_CMAKE_SYSTEM_NAME Linux' in module().triplet('linux-x86_64','renderer')
    with pytest.raises(ValueError):
        module().triplet('$(malicious)','renderer')


def test_vcpkg_profile_names_are_valid_for_every_native_architecture(tmp_path):
    import re
    for target in ('macos-arm64','macos-x86_64','linux-x86_64'):
        for profile in ('decoder','renderer'):
            name=module().profile_name(target,profile)
            assert re.fullmatch('[a-z0-9-]+',name)
            assert name in module().profile_environment({},tmp_path,target,profile)['PKG_CONFIG_LIBDIR']
    assert module().profile_name('macos-arm64','decoder')=='clipbot-macos-arm64-decoder'


def test_native_media_requires_matching_host_and_new_output(tmp_path):
    with pytest.raises(ValueError, match='matching native'):
        module().build('macos-arm64',tmp_path/'out',host_target='windows-x86_64')
    assert not (tmp_path/'out').exists()


def test_media_pkgconfig_cannot_fall_back_to_host_brew_libraries(tmp_path):
    import os
    environment = module().profile_environment({'PKG_CONFIG_PATH':'/opt/homebrew/lib/pkgconfig',
        'PKG_CONFIG_LIBDIR':'/opt/homebrew/lib/pkgconfig'}, tmp_path, 'macos-arm64', 'renderer')
    expected = str(tmp_path/'installed/renderer/clipbot-macos-arm64-renderer/lib/pkgconfig')
    assert expected in environment['PKG_CONFIG_LIBDIR'].split(os.pathsep)
    assert 'homebrew' not in environment['PKG_CONFIG_LIBDIR']
    assert environment['PKG_CONFIG_PATH'] == environment['PKG_CONFIG_LIBDIR']
    assert 'VCPKG_ENV_PASSTHROUGH PKG_CONFIG_LIBDIR' in module().triplet('macos-arm64','renderer')


def test_mac_subtitles_use_explicit_apple_font_provider():
    port = Path('packaging/native/overlays/libass/portfile.cmake').read_text()
    assert 'if(VCPKG_TARGET_IS_OSX)' in port
    assert '-Dfontconfig=disabled' in port
    assert '-Dcoretext=enabled' in port
    record = json.loads(Path('packaging/native/overlays/libass/UPSTREAM.json').read_text())
    assert record['registryCommit'] == module().BASELINE
