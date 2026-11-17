"""Ubuntu/Mint desktop integration, without privileged services."""
import os
from pathlib import Path

from .posix_integration import SingleInstance, atomic_private_file, installed_executable, safe_directory, deliver_pair_link
from ..windows_integration import parse_pair_link


def _xdg(name, fallback):
    value = os.environ.get(name)
    if value and not Path(value).is_absolute():
        raise RuntimeError('Desktop directory must use an absolute path.')
    return Path(value) if value else Path.home() / fallback


def user_directory():
    return safe_directory(_xdg('XDG_DATA_HOME', '.local/share') / 'ClipBotCompanion', private=True)


def _startup_path():
    return _xdg('XDG_CONFIG_HOME', '.config') / 'autostart/clipbot-companion.desktop'


def startup_enabled():
    path = _startup_path()
    return path.is_file() and not path.is_symlink()


def desktop_exec(executable):
    # Desktop Entry quoting is not shell quoting. Escape field-code percent too.
    value = executable.replace('%', '%%')
    for char in ('\\', '"', '`', '$'):
        value = value.replace(char, '\\' + char)
    return '"' + value + '"'


def set_startup(enabled):
    executable = installed_executable()
    path = _startup_path()
    if enabled:
        text = '[Desktop Entry]\nType=Application\nName=ClipBot Companion\nExec=' + desktop_exec(executable) + ' --background\nTerminal=false\n'
        atomic_private_file(path, text.encode('utf-8'))
    else:
        safe_directory(path.parent)
        path.unlink(missing_ok=True)
