"""macOS application paths, login launch agent and Apple URL event handling."""
import plistlib
from pathlib import Path

from .posix_integration import SingleInstance, atomic_private_file, installed_executable, safe_directory, deliver_pair_link
from ..windows_integration import parse_pair_link

_url_handler = None


def user_directory():
    return safe_directory(Path.home() / 'Library/Application Support/ClipBotCompanion', private=True)


def _startup_path():
    return Path.home() / 'Library/LaunchAgents/com.yourcompany.clipbot.companion.plist'


def startup_enabled():
    path = _startup_path()
    return path.is_file() and not path.is_symlink()


def set_startup(enabled):
    executable = installed_executable()
    path = _startup_path()
    if enabled:
        value = {'Label': 'com.yourcompany.clipbot.companion', 'ProgramArguments': [executable, '--background'], 'RunAtLoad': True, 'ProcessType': 'Interactive'}
        atomic_private_file(path, plistlib.dumps(value))
    else:
        safe_directory(path.parent)
        path.unlink(missing_ok=True)


def install_url_handler(on_error):
    # Pystray's macOS backend already depends on PyObjC/AppKit. Import only on Mac.
    from AppKit import NSAppleEventManager, NSObject
    global _url_handler

    class ClipBotURLHandler(NSObject):
        def handleGetURLEvent_withReplyEvent_(self, event, reply):
            try:
                value = event.paramDescriptorForKeyword_(int.from_bytes(b'----', 'big')).stringValue()
                deliver_pair_link(str(value))
            except Exception:
                on_error()

    _url_handler = ClipBotURLHandler.alloc().init()
    event_code = int.from_bytes(b'GURL', 'big')
    NSAppleEventManager.sharedAppleEventManager().setEventHandler_andSelector_forEventClass_andEventID_(_url_handler, 'handleGetURLEvent:withReplyEvent:', event_code, event_code)
