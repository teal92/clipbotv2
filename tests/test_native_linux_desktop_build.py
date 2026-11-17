import importlib

import pytest


def module():
    return importlib.import_module('tools.build_native_linux_desktop')


def test_linux_desktop_source_build_rejects_other_hosts_before_creating_output(tmp_path):
    with pytest.raises(ValueError,match='matching Linux'):
        module().build(tmp_path/'output',host_target='macos-arm64')
    assert not (tmp_path/'output').exists()


def test_desktop_build_does_not_allow_resolver_or_meson_network_fallback(tmp_path):
    command=module().wheel_command(tmp_path/'python',tmp_path/'source',tmp_path/'wheels')
    for flag in ('--no-index','--no-deps','--no-build-isolation'):
        assert flag in command
    assert '--config-settings=setup-args=--wrap-mode=nodownload' in command
    assert '--config-settings=setup-args=-Dtests=false' in command


def test_desktop_sources_build_cairo_before_gobject():
    assert module().SOURCE_ORDER == ('pycairo','pygobject')
