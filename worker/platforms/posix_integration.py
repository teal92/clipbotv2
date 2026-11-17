"""Per-user desktop integration; incoming application URLs remain data."""
import os
import stat
import sys
import tempfile
import time
from pathlib import Path

from ..windows_integration import parse_pair_link
from ..client import configured_origin



def safe_directory(path, private=False):
    path = Path(path).absolute()
    for item in (path, *path.parents):
        if item.is_symlink() or (hasattr(item, 'is_junction') and item.is_junction()):
            raise RuntimeError('Companion directory is unsafe.')
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    if hasattr(os, 'getuid'):
        info = path.stat()
        if info.st_uid != os.getuid() or info.st_mode & (0o077 if private else 0o022):
            raise RuntimeError('Companion directory permissions are unsafe.')
    return path


def atomic_private_file(path, data):
    path = Path(path)
    parent = safe_directory(path.parent)
    if path.is_symlink():
        raise RuntimeError('Companion settings path is unsafe.')
    fd, temporary = tempfile.mkstemp(prefix='.clipbot-', dir=parent)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


class SingleInstance:
    def __init__(self, root=None):
        import fcntl
        if root is None:
            from . import integration
            root = integration().user_directory()
        directory = safe_directory(root, private=True)
        self.fd = os.open(directory / 'companion.lock', os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
        self.primary = False
        try:
            info = os.fstat(self.fd)
            if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_nlink != 1 or info.st_mode & 0o077:
                raise RuntimeError('Companion lock is unsafe.')
            try:
                fcntl.flock(self.fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                self.primary = True
            except BlockingIOError:
                pass
        except Exception:
            self.close()
            raise

    def close(self):
        if self.fd is not None:
            os.close(self.fd)
            self.fd = None

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


def installed_executable():
    if not getattr(sys, 'frozen', False):
        raise RuntimeError('Startup is available in the installed companion.')
    path = Path(sys.executable)
    if not path.is_absolute() or any(c in str(path) for c in '\n\r\0'):
        raise RuntimeError('The installed companion path is invalid.')
    return str(path)


def deliver_pair_link(value, root=None):
    code = parse_pair_link(value)
    from ..credentials import save
    if root is None:
        from . import integration
        root = integration().user_directory()
    save(Path(root) / 'pair-handoff.bin', configured_origin(), code)


def consume_pair_link(root):
    from ..credentials import delete, load
    from .secrets import private_path
    path = private_path(Path(root) / 'pair-handoff.bin')
    if not path.exists():
        return None
    age = time.time() - path.stat().st_mtime
    # Filesystem stamps can lead the process clock slightly; the server still
    # independently enforces the one-time code's ten-minute expiry.
    value = load(path, configured_origin()) if -5 <= age <= 600 else None
    delete(path, configured_origin())
    return value
