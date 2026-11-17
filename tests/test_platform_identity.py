import importlib
import sys

import pytest

from worker.tools import media_tool


@pytest.mark.parametrize('system,machine,target', [
    ('Darwin', 'arm64', 'macos-arm64'),
    ('Darwin', 'aarch64', 'macos-arm64'),
    ('Darwin', 'x86_64', 'macos-x86_64'),
    ('Linux', 'x86_64', 'linux-x86_64'),
    ('Windows', 'AMD64', 'windows-x86_64'),
])
def test_platform_target_aliases(system, machine, target):
    identity = importlib.import_module('worker.platforms.identity')
    assert identity.platform_target(system, machine) == target


@pytest.mark.parametrize('system,machine', [('Linux', 'arm64'), ('Windows', 'ARM64'), ('FreeBSD', 'x86_64'), ('Darwin', '../arm64')])
def test_unknown_platform_rejected(system, machine):
    identity = importlib.import_module('worker.platforms.identity')
    with pytest.raises(ValueError):
        identity.platform_target(system, machine)


@pytest.mark.parametrize('system', ['darwin', 'linux'])
def test_frozen_tool_native_filename(monkeypatch, tmp_path, system):
    monkeypatch.setattr(sys, 'platform', system)
    monkeypatch.setattr(sys, 'frozen', True, raising=False)
    monkeypatch.setattr(sys, '_MEIPASS', str(tmp_path), raising=False)
    (tmp_path / 'bin').mkdir()
    tool = tmp_path / 'bin' / 'ffprobe'
    tool.write_bytes(b'fixture')
    assert media_tool('ffprobe') == str(tool.resolve())


def test_frozen_missing_native_tool_rejects_windows_substitute(monkeypatch, tmp_path):
    monkeypatch.setattr(sys, 'platform', 'darwin')
    monkeypatch.setattr(sys, 'frozen', True, raising=False)
    monkeypatch.setattr(sys, '_MEIPASS', str(tmp_path), raising=False)
    (tmp_path / 'bin').mkdir()
    (tmp_path / 'bin' / 'ffprobe.exe').write_bytes(b'wrong-os')
    with pytest.raises(RuntimeError, match='missing'):
        media_tool('ffprobe')
