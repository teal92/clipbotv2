"""Native secret service selection. Never invoke command-line password tools."""
import hashlib
import os
import stat
import sys
import tempfile
from pathlib import Path

MARKER = b'ClipBot native credential reference v1\n'


def backend():
    if sys.platform == 'darwin':
        from .macos_secrets import Keychain
        return Keychain()
    if sys.platform == 'linux':
        from .linux_secrets import SecretService
        return SecretService()
    raise RuntimeError('Native secure storage is unavailable.')


def private_path(path):
    path = Path(path).absolute()
    for item in (path, *path.parents):
        if item.is_symlink() or (hasattr(item, 'is_junction') and item.is_junction()):
            raise RuntimeError('Secure storage path is unsafe.')
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    if hasattr(os, 'getuid'):
        info = path.parent.stat()
        if info.st_uid != os.getuid() or info.st_mode & 0o077:
            raise RuntimeError('Companion storage must be private to your user account.')
        if path.exists():
            info = path.stat()
            if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077 or info.st_nlink != 1:
                raise RuntimeError('Secure storage reference is unsafe.')
    return path


def entry_key(path, origin):
    return hashlib.sha256((str(path) + '\n' + origin).encode('utf-8')).hexdigest()


def save(path, origin, token):
    try:
        path = private_path(path)
        vault = backend()
        vault.put(entry_key(path, origin), token)
        fd, temporary = tempfile.mkstemp(prefix='.credential-', dir=path.parent)
        try:
            with os.fdopen(fd, 'wb') as stream:
                stream.write(MARKER)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, path)
        finally:
            Path(temporary).unlink(missing_ok=True)
    except Exception:
        raise RuntimeError('Secure credential storage is unavailable. Unlock your login keychain or desktop keyring and try again.') from None


def load(path, origin):
    path = private_path(path)
    if not path.is_file() or path.stat().st_size != len(MARKER) or path.read_bytes() != MARKER:
        return None
    return backend().get(entry_key(path, origin))


def delete(path, origin):
    try:
        path = private_path(path)
        backend().remove(entry_key(path, origin))
        path.unlink(missing_ok=True)
    except Exception:
        raise RuntimeError('Secure credential removal failed. Unlock your login keychain or desktop keyring and try again.') from None
