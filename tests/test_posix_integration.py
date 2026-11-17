import importlib
import os
import plistlib
import sys
from pathlib import Path

import pytest


def test_linux_startup_escapes_executable_and_does_not_enable_by_default(tmp_path, monkeypatch):
    module = importlib.import_module('worker.platforms.linux')
    monkeypatch.setattr(Path, 'home', lambda: tmp_path)
    monkeypatch.delenv('XDG_CONFIG_HOME', raising=False)
    monkeypatch.setattr(sys, 'frozen', True, raising=False)
    monkeypatch.setattr(sys, 'executable', str(tmp_path / 'a $b% c' / 'ClipBotCompanion'))
    assert module.startup_enabled() is False
    module.set_startup(True)
    path = tmp_path / '.config/autostart/clipbot-companion.desktop'
    content = path.read_text()
    assert '\\$b%% c' in content
    assert '--background' in content
    assert module.startup_enabled() is True
    module.set_startup(False)
    assert not path.exists()


def test_macos_startup_is_per_user_structured_arguments(tmp_path, monkeypatch):
    module = importlib.import_module('worker.platforms.macos')
    monkeypatch.setattr(Path, 'home', lambda: tmp_path)
    monkeypatch.setattr(sys, 'frozen', True, raising=False)
    executable = str(tmp_path / 'App With Spaces.app/Contents/MacOS/ClipBotCompanion')
    monkeypatch.setattr(sys, 'executable', executable)
    assert module.startup_enabled() is False
    module.set_startup(True)
    data = plistlib.loads((tmp_path / 'Library/LaunchAgents/com.yourcompany.clipbot.companion.plist').read_bytes())
    assert data['ProgramArguments'] == [executable, '--background']
    assert data['RunAtLoad'] is True
    assert not data.get('KeepAlive')
    module.set_startup(False)
    assert module.startup_enabled() is False


@pytest.mark.skipif(os.name == 'nt', reason='requires native POSIX file locking')
def test_posix_single_instance_lock_and_private_file(tmp_path):
    module = importlib.import_module('worker.platforms.posix_integration')
    first, second = module.SingleInstance(tmp_path), module.SingleInstance(tmp_path)
    try:
        assert first.primary is True
        assert second.primary is False
        assert (tmp_path / 'companion.lock').stat().st_mode & 0o077 == 0
        first.close()
        with module.SingleInstance(tmp_path) as third:
            assert third.primary is True
    finally:
        first.close()
        second.close()


@pytest.mark.parametrize('value', [
    'clipbot-companion://pair?code=' + 'a' * 24 + '&code=' + 'b' * 24,
    'clipbot-companion://pair?code=' + 'a' * 24 + '#fragment',
    'clipbot-companion://pair?code=' + 'a' * 24 + '&command=rm',
])
def test_posix_handoff_rejects_bad_links_before_storage(value):
    module = importlib.import_module('worker.platforms.posix_integration')
    with pytest.raises(ValueError):
        module.deliver_pair_link(value)
