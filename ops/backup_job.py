"""Fixed local encrypted backup job shared by Windows scheduling and private C2."""
import json
import os
import re
import subprocess
import sys
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from . import encrypted_backup as backup

TARGET = 'YOUR-RENDER-SERVICE-ID@ssh.oregon.render.com'
FAILURE = 'Backup failed safely. Check the private backup task.'
NAME = re.compile(r'clipbot-[0-9]{8}T[0-9]{6}Z-[a-f0-9]{8}\.cbk')


class BackupBusy(Exception):
    pass


def now():
    return datetime.now(timezone.utc).isoformat()


def hidden():
    return {'creationflags': subprocess.CREATE_NO_WINDOW} if os.name == 'nt' else {}


@contextmanager
def exclusive_run(destination):
    """An OS-held file lock also prevents concurrent manual/weekly processes."""
    path = backup.safe_path(Path(destination) / 'backup-run.lock')
    with path.open('a+b') as stream:
        if not path.stat().st_size:
            stream.write(b'0'); stream.flush()
        stream.seek(0)
        try:
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            raise BackupBusy() from None
        try:
            yield
        finally:
            stream.seek(0)
            if os.name == 'nt':
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


def read_json(path, maximum=16384):
    path = backup.safe_path(path)
    with path.open('rb') as stream:
        data = stream.read(maximum + 1)
    if len(data) > maximum:
        raise ValueError('Oversized private configuration.')
    result = json.loads(data)
    if not isinstance(result, dict):
        raise ValueError('Invalid private configuration.')
    return result


def previous_success(path):
    try:
        value = read_json(path).get('lastSuccessful')
        if not isinstance(value, dict) or not NAME.fullmatch(value.get('file', '')):
            return None
        completed = datetime.fromisoformat(value['completedAt'])
        if completed.tzinfo is None or any(type(value.get(k)) is not int or value[k] <= 0 for k in ('tablesCompared', 'encryptedBytes')):
            return None
        return {k: value[k] for k in ('file', 'completedAt', 'tablesCompared', 'encryptedBytes')}
    except (OSError, ValueError, TypeError, KeyError):
        return None


def python_executable():
    executable = backup.safe_path(Path(sys.executable).with_name('python.exe') if os.name == 'nt' else sys.executable)
    if not executable.is_file():
        raise ValueError('Verified Python environment is unavailable.')
    return executable


def save_status(path, state):
    """Replace metadata atomically; immutable encrypted archives are never replaced."""
    path = backup.safe_path(path)
    temporary = backup.safe_path(path.parent / ('.status-' + os.urandom(16).hex() + '.tmp'))
    try:
        with temporary.open('xb') as stream:
            backup.restrict_permissions(temporary)
            stream.write(json.dumps(state, sort_keys=True).encode())
            stream.flush(); os.fsync(stream.fileno())
        backup.safe_path(path)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def run_job(config_path, destination, key_path, runner=subprocess.run):
    destination = backup.safe_path(destination)
    destination.mkdir(parents=True, exist_ok=True)
    backup.restrict_permissions(destination, True)
    try:
        with exclusive_run(destination):
            status_path = backup.safe_path(destination / 'backup-status.json')
            state = {'version': 1, 'state': 'running', 'startedAt': now(), 'completedAt': None,
                     'lastSuccessful': previous_success(status_path), 'error': None}
            def save():
                save_status(status_path, state)
            save()
            stage = 'key-read'
            try:
                key_path = backup.safe_path(key_path)
                if not key_path.is_file():
                    raise ValueError('Existing recovery key is required.')
                stage = 'key-unlock'
                master = backup.master_key(key_path, create=False)
                stage = 'config-read'
                config = read_json(config_path)
                if set(config) != {'identity', 'knownHosts', 'target'} or config['target'] != TARGET:
                    raise ValueError('Unexpected private backup configuration.')
                identity, hosts = (backup.safe_path(config[k]) for k in ('identity', 'knownHosts'))
                if not identity.is_file() or not hosts.is_file():
                    raise ValueError('Pinned access is unavailable.')
                stage = 'python-check'
                args = [str(python_executable()), '-m', 'ops.encrypted_backup', 'backup', '--destination', str(destination),
                        '--key-file', str(key_path), '--identity', str(identity), '--known-hosts', str(hosts), '--target', TARGET]
                stage = 'encrypted-snapshot'
                result = runner(args, cwd=Path(__file__).resolve().parents[1], capture_output=True, text=True,
                                timeout=120, **hidden())
                if result.returncode != 0 or not isinstance(result.stdout, str) or len(result.stdout) > 8192:
                    raise ValueError('Backup process did not confirm completion.')
                stage = 'receipt-check'
                report = json.loads(result.stdout)
                name = report.get('backupFile') if isinstance(report, dict) else None
                if report.get('backupSaved') is not True or not isinstance(name, str) or not NAME.fullmatch(name):
                    raise ValueError('Backup filename was not verified.')
                path = backup.safe_path(destination / name)
                with path.open('rb') as stream:
                    encrypted = stream.read(backup.MAX_ENVELOPE + 1)
                if len(encrypted) != report.get('encryptedBytes') or len(encrypted) > backup.MAX_ENVELOPE:
                    raise ValueError('Backup size differs from the receipt.')
                stage = 'independent-verification'
                checked = backup.drill_backup(encrypted, master)
                if checked['tablesCompared'] != report.get('tablesCompared'):
                    raise ValueError('Backup content differs from the receipt.')
                state.update(state='succeeded', completedAt=now(), error=None)
                state['lastSuccessful'] = {'file': name, 'completedAt': state['completedAt'],
                                           'tablesCompared': checked['tablesCompared'], 'encryptedBytes': len(encrypted)}
                save()
                return 0
            except Exception as error:
                failure = type(error).__name__
                allowed = {'OSError', 'PermissionError', 'ValueError', 'BackupRejected', 'TimeoutExpired', 'FileNotFoundError', 'JSONDecodeError'}
                save_status(destination / 'backup-diagnostic.json', {'stage': stage, 'failureClass': failure if failure in allowed else 'Exception', 'at': now()})
                state.update(state='failed', completedAt=now(), error=FAILURE)
                save()
                return 1
    except BackupBusy:
        return 2


def main():
    if os.name != 'nt' or len(sys.argv) != 1:
        return 1
    destination = Path.home() / 'Documents' / 'ClipBotBackups'
    try:
        # Background sessions may have different environment-derived app-data paths.
        locations = read_json(destination / 'backup-location.json')
        if set(locations) != {'configFile', 'keyFile'} or any(not isinstance(v, str) or not 1 <= len(v) <= 2048 or not Path(v).is_absolute() for v in locations.values()):
            return 1
        return run_job(backup.safe_path(locations['configFile']), destination, backup.safe_path(locations['keyFile']))
    except Exception:
        return 1


if __name__ == '__main__':
    sys.exit(main())
