import importlib
from pathlib import Path

import pytest


def module():
    return importlib.import_module('tools.build_native_pyav')


def test_mac_decoder_reserves_space_for_portable_library_paths():
    assert module().native_link_flags('macos-arm64') == '-Wl,-headerpad_max_install_names'
    assert module().native_link_flags('macos-x86_64') == '-Wl,-headerpad_max_install_names'
    assert module().native_link_flags('linux-x86_64') == ''
    with pytest.raises(ValueError):
        module().native_link_flags('unknown')


def test_native_decoder_build_cannot_use_other_host_or_create_output(tmp_path):
    with pytest.raises(ValueError,match='matching native'):
        module().build('macos-arm64',tmp_path/'media',tmp_path/'out',host_target='windows-x86_64')
    assert not (tmp_path/'out').exists()


def test_repaired_decoder_wheel_must_match_version_target_and_os_floor(tmp_path):
    check = module().validate_wheel_name
    assert check(tmp_path/'av-18.0.0-cp311-abi3-macosx_14_0_arm64.whl','macos-arm64') is None
    for name in ['av-18.0.0-cp311-abi3-win_amd64.whl','av-18.0.0-cp311-abi3-macosx_15_0_arm64.whl',
                 'av-17.0.0-cp311-abi3-macosx_14_0_arm64.whl','unexpected-18.0.0-py3-none-any.whl']:
        with pytest.raises(ValueError):
            check(tmp_path/name,'macos-arm64')


def test_native_decoder_receipt_cannot_point_outside_its_build(tmp_path):
    target='macos-arm64'
    receipt={'target':target,'registryCommit':'c52f7bd748185ef0e0daf033d9f2ddfc8a3449ea',
             'mediaFeatureChecksPassed':True,'profiles':{'decoder':{'triplet':'clipbot-macos-arm64-decoder',
             'installed':str(tmp_path.parent/'unrelated')}}}
    with pytest.raises(ValueError,match='prefix'):
        module().decoder_prefix(tmp_path,receipt,target)


def test_native_decoder_requires_actual_checked_media_receipt(tmp_path):
    with pytest.raises(ValueError):
        module().decoder_prefix(tmp_path,{'target':'macos-x86_64'},'macos-arm64')
