"""Bounded, encrypted off-server snapshots; no live restore or automatic pruning."""
import argparse
import base64
import csv
import ctypes
import hashlib
import io
import json
import os
import re
import secrets
import shlex
import sqlite3
import stat
import struct
import subprocess
import sys
import tempfile
import time
import zipfile
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

MAX_ARCHIVE = 32 * 1024 * 1024
MAX_ENVELOPE = MAX_ARCHIVE + 8192
MAGIC = b'CLIPBOT-BACKUP\x01'
RECOVERY_NAMES = frozenset('''CLIPBOT_ORIGIN CLIPBOT_ADMIN_USER_ID
CLIPBOT_TOKEN_ENCRYPTION_KEY CLIPBOT_C2_SERVICE_KEY
TWITCH_CLIENT_ID TWITCH_CLIENT_SECRET KICK_CLIENT_ID KICK_CLIENT_SECRET
META_APP_ID META_APP_SECRET META_GRAPH_VERSION TIKTOK_CLIENT_KEY TIKTOK_CLIENT_SECRET
STRIPE_SECRET_KEY STRIPE_WEBHOOK_SECRET STRIPE_PRICE_STARTER STRIPE_PRICE_CREATOR
STRIPE_PRICE_PRO STRIPE_PORTAL_CONFIGURATION CLIPBOT_BILLING_MODE CLIPBOT_LIVE_BILLING_ACCEPTED
STRIPE_LIVE_SECRET_KEY STRIPE_LIVE_WEBHOOK_SECRET STRIPE_LIVE_PRICE_STARTER STRIPE_LIVE_PRICE_CREATOR
STRIPE_LIVE_PRICE_PRO STRIPE_LIVE_PORTAL_CONFIGURATION
STRIPE_CUSTOM_PRODUCT STRIPE_CUSTOM_PRICES STRIPE_LIVE_CUSTOM_PRODUCT STRIPE_LIVE_CUSTOM_PRICES
CLIPBOT_REPORT_EMAIL CLIPBOT_REPORT_FROM CLIPBOT_REPORT_SMTP_HOST
CLIPBOT_REPORT_SMTP_USERNAME CLIPBOT_REPORT_SMTP_PASSWORD CLIPBOT_REPORT_SMTP_PORT
ANTHROPIC_API_KEY CLIPBOT_GLOBAL_MONTHLY_USD CLIPBOT_GLOBAL_DAILY_USD
CLIPBOT_PUBLIC_SIGNUP CLIPBOT_ENFORCE_CUSTOMER_ACCESS CLIPBOT_EDGE_VERIFIED
CLIPBOT_CUSTOMER_ANALYSIS_ENABLED CLIPBOT_MAIL_DAILY_LIMIT CLIPBOT_MAIL_MONTHLY_LIMIT
CLIPBOT_TRUSTED_EDGE CLIPBOT_EDGE_SECRET CLIPBOT_TRUSTED_PROXY_CIDRS KICK_CHAT_WEBHOOK_ENABLED
CLIPBOT_COMPANION_PUBLIC_RELEASE CLIPBOT_COMPANION_DOWNLOAD_URL CLIPBOT_COMPANION_VERSION CLIPBOT_COMPANION_SHA256'''.split())


class BackupRejected(ValueError):
    """Safe public error; never includes paths, records or credentials."""


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True).encode()


def safe_path(path):
    path = Path(path)
    if '..' in path.parts:
        raise BackupRejected('Unsafe path.')
    path = path.absolute()
    for component in (path, *path.parents):
        try:
            info = component.lstat()
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(info.st_mode) or getattr(info, 'st_file_attributes', 0) & 0x400:
            raise BackupRejected('Linked or reparse paths are forbidden.')
    return path


def process_options():
    return {'creationflags': subprocess.CREATE_NO_WINDOW} if os.name == 'nt' else {}


def restrict_permissions(path, directory=False):
    if os.name != 'nt':
        os.chmod(path, 0o700 if directory else 0o600)
        return
    # Replace inherited/existing grants, then grant only the current Windows SID.
    result = subprocess.run(['whoami', '/user', '/fo', 'csv', '/nh'], capture_output=True, check=True, text=True, **process_options())
    sid = next(csv.reader(io.StringIO(result.stdout)))[1]
    if not re.fullmatch(r'S-1-[0-9-]+', sid):
        raise BackupRejected('Unable to establish private permissions.')
    for args in (['/reset'], ['/inheritance:r'], ['/grant:r', '*'+sid+(':(OI)(CI)F' if directory else ':F')]):
        subprocess.run(['icacls', str(path), *args], capture_output=True, check=True, **process_options())


@contextmanager
def private_temp():
    with tempfile.TemporaryDirectory(prefix='clipbot-recovery-') as name:
        folder = safe_path(name)
        restrict_permissions(folder, True)
        yield folder


def seal(payload, key, metadata):
    if len(key) != 32 or len(payload) > MAX_ARCHIVE + (2048 if metadata.get('kind') == 'wrapped' else 0):
        raise BackupRejected('Backup exceeds its size limit or key is invalid.')
    if metadata.get('version') != 1 or metadata.get('kind') not in ('snapshot', 'wrapped'):
        raise BackupRejected('Unsupported envelope metadata.')
    header = canonical(metadata)
    if len(header) > 1024:
        raise BackupRejected('Envelope metadata exceeds its limit.')
    prefix = MAGIC + struct.pack('>I', len(header)) + header
    nonce = secrets.token_bytes(12)
    return prefix + nonce + AESGCM(key).encrypt(nonce, payload, prefix)


def open_envelope(envelope, key):
    try:
        if len(key) != 32 or len(envelope) > MAX_ENVELOPE or not envelope.startswith(MAGIC):
            raise ValueError()
        size = struct.unpack('>I', envelope[len(MAGIC):len(MAGIC)+4])[0]
        if not 0 < size <= 1024:
            raise ValueError()
        end = len(MAGIC) + 4 + size
        metadata = json.loads(envelope[len(MAGIC)+4:end])
        if metadata.get('version') != 1 or metadata.get('kind') not in ('snapshot', 'wrapped'):
            raise ValueError()
        nonce = envelope[end:end+12]
        payload = AESGCM(key).decrypt(nonce, envelope[end+12:], envelope[:end])
        if len(payload) > MAX_ARCHIVE + (2048 if metadata['kind'] == 'wrapped' else 0):
            raise ValueError()
        return payload, metadata
    except Exception:
        raise BackupRejected('Backup authentication or format validation failed.') from None


def table_state(db):
    state = {}
    for (name,) in db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"):
        hashes = []
        for row in db.execute('SELECT * FROM "' + name.replace('"', '""') + '"'):
            values = [({'bytes': value.hex()} if isinstance(value, bytes) else value) for value in row]
            hashes.append(hashlib.sha256(canonical(values)).digest())
        state[name] = {'rows': len(hashes), 'sha256': hashlib.sha256(b''.join(sorted(hashes))).hexdigest()}
    schema = list(db.execute('SELECT type,name,tbl_name,sql FROM sqlite_master ORDER BY type,name'))
    return {'tables': state, 'schemaSha256': hashlib.sha256(canonical(schema)).hexdigest()}


def valid_db(db):
    if db.execute('PRAGMA integrity_check').fetchall() != [('ok',)] or db.execute('PRAGMA foreign_key_check').fetchall():
        raise BackupRejected('Database integrity validation failed.')


def snapshot_archive(source_path, environment):
    source_path = safe_path(source_path)
    if not source_path.is_file() or source_path.stat().st_size > MAX_ARCHIVE:
        raise BackupRejected('Database missing or above snapshot limit.')
    settings = {name: environment[name] for name in sorted(RECOVERY_NAMES) if environment.get(name)}
    if any(not isinstance(v, str) or len(v.encode()) > 16384 for v in settings.values()):
        raise BackupRejected('Recovery settings exceed limits.')
    recovery = canonical(settings)
    if len(recovery) > 256 * 1024:
        raise BackupRejected('Recovery settings exceed limits.')
    with private_temp() as folder:
        target = folder / 'database.db'
        source = sqlite3.connect(source_path.as_uri() + '?mode=ro', uri=True, timeout=5)
        backup = sqlite3.connect(target)
        try:
            source.execute('BEGIN')
            # Establish the read transaction before copying; concurrent WAL writes
            # must not advance the source snapshot used for the hash comparison.
            source.execute('SELECT COUNT(*) FROM sqlite_master').fetchone()
            started = time.monotonic()
            def progress(status, remaining, total):
                if total * source.execute('PRAGMA page_size').fetchone()[0] > MAX_ARCHIVE or time.monotonic() - started > 60:
                    raise BackupRejected('Snapshot bounds exceeded.')
            source.backup(backup, pages=256, progress=progress)
            valid_db(backup)
            manifest = table_state(backup)
            if table_state(source) != manifest:
                raise BackupRejected('Snapshot consistency validation failed.')
        finally:
            backup.close()
            source.close()
        if target.stat().st_size + len(recovery) + len(canonical(manifest)) + 4096 > MAX_ARCHIVE:
            raise BackupRejected('Snapshot archive exceeds limit.')
        data = target.read_bytes()
        manifest.update(version=1, members={'database.db': hashlib.sha256(data).hexdigest(), 'recovery.json': hashlib.sha256(recovery).hexdigest()})
        stream = io.BytesIO()
        with zipfile.ZipFile(stream, 'w', compression=zipfile.ZIP_STORED) as archive:
            archive.writestr('database.db', data)
            archive.writestr('recovery.json', recovery)
            archive.writestr('manifest.json', canonical(manifest))
        payload = stream.getvalue()
        if len(payload) > MAX_ARCHIVE:
            raise BackupRejected('Snapshot archive exceeds limit.')
        return payload


def drill_archive(payload):
    try:
        if len(payload) > MAX_ARCHIVE:
            raise ValueError()
        with zipfile.ZipFile(io.BytesIO(payload)) as archive:
            entries = archive.infolist()
            if len(entries) != 3 or {entry.filename for entry in entries} != {'database.db', 'recovery.json', 'manifest.json'}:
                raise ValueError()
            if any(entry.compress_type != zipfile.ZIP_STORED or entry.file_size > MAX_ARCHIVE for entry in entries):
                raise ValueError()
            if sum(entry.file_size for entry in entries) > MAX_ARCHIVE:
                raise ValueError()
            files = {entry.filename: archive.read(entry) for entry in entries}
        manifest = json.loads(files['manifest.json'])
        settings = json.loads(files['recovery.json'])
        if manifest['version'] != 1 or not isinstance(settings, dict) or set(settings) - RECOVERY_NAMES:
            raise ValueError()
        if any(not isinstance(value, str) or len(value.encode()) > 16384 for value in settings.values()):
            raise ValueError()
        if set(manifest['members']) != {'database.db', 'recovery.json'}:
            raise ValueError()
        for name, digest in manifest['members'].items():
            if hashlib.sha256(files[name]).hexdigest() != digest:
                raise ValueError()
        with private_temp() as folder:
            path = folder / 'database.db'
            atomic_write(path, files['database.db'])
            db = sqlite3.connect(path.as_uri()+'?mode=ro', uri=True)
            try:
                valid_db(db)
                state = table_state(db)
                if state != {k: manifest[k] for k in ('tables', 'schemaSha256')}:
                    raise ValueError()
            finally:
                db.close()
        return {'integrityOk': True, 'foreignKeysOk': True, 'allTableContentMatches': True,
                'tablesCompared': len(state['tables']), 'recoverySettingsPresent': bool(settings),
                'tokenEncryptionKeyPresent': bool(settings.get('CLIPBOT_TOKEN_ENCRYPTION_KEY')),
                'operatorKeyPresent': bool(settings.get('CLIPBOT_C2_SERVICE_KEY'))}
    except Exception:
        raise BackupRejected('Archive integrity or recovery validation failed.') from None


def atomic_write(path, data):
    path = safe_path(path)
    if len(data) > MAX_ENVELOPE or path.exists() or not path.parent.is_dir():
        raise BackupRejected('Output exists, parent missing, or output exceeds limit.')
    temporary = path.parent / ('.backup-' + secrets.token_hex(16) + '.tmp')
    try:
        descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, 'wb') as handle:
            restrict_permissions(temporary)
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        safe_path(path)
        # Hard-link promotion is atomic and refuses any existing destination.
        os.link(temporary, path)
    except Exception:
        raise BackupRejected('Private atomic output write failed.') from None
    finally:
        temporary.unlink(missing_ok=True)


# LOCAL OPERATIONS: remote script ends before this marker.
class WindowsDPAPI:
    def _crypt(self, data, decrypt=False):
        if os.name != 'nt':
            raise BackupRejected('Production master keys require Windows DPAPI.')
        from ctypes import wintypes
        class Blob(ctypes.Structure):
            _fields_ = [('size', wintypes.DWORD), ('data', ctypes.POINTER(ctypes.c_ubyte))]
        storage = (ctypes.c_ubyte * len(data)).from_buffer_copy(data)
        incoming, outgoing = Blob(len(data), storage), Blob()
        crypt = ctypes.WinDLL('crypt32', use_last_error=True)
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        kernel.LocalFree.argtypes = [ctypes.c_void_p]
        kernel.LocalFree.restype = ctypes.c_void_p
        # CRYPTPROTECT_UI_FORBIDDEN; no machine-wide flag: current user only.
        operation = crypt.CryptUnprotectData if decrypt else crypt.CryptProtectData
        operation.argtypes = [ctypes.POINTER(Blob), ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(Blob)]
        operation.restype = wintypes.BOOL
        if not operation(ctypes.byref(incoming), None, None, None, None, 1, ctypes.byref(outgoing)):
            raise BackupRejected('Windows key protection failed.')
        try:
            return ctypes.string_at(outgoing.data, outgoing.size)
        finally:
            kernel.LocalFree(outgoing.data)

    def protect(self, data):
        return self._crypt(data)

    def unprotect(self, data):
        return self._crypt(data, True)


def master_key(path, protector=None, create=True):
    protector = WindowsDPAPI() if protector is None else protector
    path = safe_path(path)
    if path.exists():
        if path.stat().st_size > 4096:
            raise BackupRejected('Invalid protected master key.')
        restrict_permissions(path)
        key = protector.unprotect(path.read_bytes())
    else:
        if not create:
            raise BackupRejected('Protected master key is missing.')
        path.parent.mkdir(parents=True, exist_ok=True)
        safe_path(path.parent)
        restrict_permissions(path.parent, True)
        key = secrets.token_bytes(32)
        atomic_write(path, protector.protect(key))
    if len(key) != 32:
        raise BackupRejected('Invalid protected master key.')
    return key


def remote_script():
    source = Path(__file__).read_text(encoding='utf-8').split('# LOCAL OPERATIONS:')[0]
    return source + '''
try:
    key = sys.stdin.buffer.read(33)
    if len(key) != 32: raise BackupRejected('Invalid session key.')
    settings = dict(os.environ)
    if not settings.get('CLIPBOT_C2_SERVICE_KEY'):
        configured = settings.get('CLIPBOT_C2_SERVICE_KEY_FILE', '/var/data/clipbot-c2.key')
        if configured != '/var/data/clipbot-c2.key': raise BackupRejected('Unsupported operator key file.')
        path = safe_path('/var/data/clipbot-c2.key')
        if path.exists():
            if path.stat().st_size > 256: raise BackupRejected('Invalid operator key file.')
            settings['CLIPBOT_C2_SERVICE_KEY'] = path.read_text(encoding='utf-8').strip()
    archive = snapshot_archive(Path('/var/data/clipbot.db'), settings)
    sys.stdout.buffer.write(seal(archive, key, {'kind': 'snapshot', 'version': 1}))
except Exception:
    sys.stderr.write('Encrypted snapshot failed safely.\\n')
    sys.exit(1)
'''


def wrap_remote(remote, session, master):
    # Verify remote AEAD before saving; disk never receives decrypted archive.
    _, metadata = open_envelope(remote, session)
    if metadata['kind'] != 'snapshot':
        raise BackupRejected('Unexpected remote envelope.')
    return seal(session + remote, master, {'kind': 'wrapped', 'version': 1})


def drill_backup(envelope, master):
    payload, metadata = open_envelope(envelope, master)
    if metadata['kind'] != 'wrapped' or len(payload) < 32:
        raise BackupRejected('Unexpected backup envelope.')
    archive, inner = open_envelope(payload[32:], payload[:32])
    if inner['kind'] != 'snapshot':
        raise BackupRejected('Unexpected snapshot envelope.')
    return drill_archive(archive)


def fetch_remote(identity, known_hosts, target, session):
    if not re.fullmatch(r'srv-[a-z0-9]+@ssh\.[a-z0-9-]+\.render\.com', target):
        raise BackupRejected('Unexpected SSH target.')
    identity, known_hosts = safe_path(identity), safe_path(known_hosts)
    if not identity.is_file() or not known_hosts.is_file():
        raise BackupRejected('Pinned SSH credentials are missing.')
    args = ['ssh', '-i', str(identity), '-o', 'BatchMode=yes', '-o', 'StrictHostKeyChecking=yes',
            '-o', 'ConnectTimeout=15', '-o', 'UserKnownHostsFile='+str(known_hosts), target,
            'python -c ' + shlex.quote(remote_script())]
    # Discard SSH diagnostics entirely, avoiding unbounded or sensitive logs.
    process = subprocess.Popen(args, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, **process_options())
    try:
        process.stdin.write(session)
        process.stdin.close()
        # Watchdog also bounds a stalled read; diagnostics are never printed.
        import threading
        timer = threading.Timer(90, process.kill)
        timer.start()
        try:
            output = process.stdout.read(MAX_ENVELOPE + 1)
            if len(output) > MAX_ENVELOPE:
                raise BackupRejected('Remote snapshot exceeds limit.')
            if process.wait(timeout=5) != 0:
                raise BackupRejected('Private remote snapshot failed.')
        finally:
            timer.cancel()
        return output
    finally:
        if process.poll() is None:
            process.kill()
        process.wait()
        process.stdout.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('backup', 'drill'))
    parser.add_argument('--destination', default=str(Path.home()/'Documents'/'ClipBotBackups'))
    parser.add_argument('--key-file', default=str(Path(os.environ.get('LOCALAPPDATA', ''))/'ClipBotRecovery'/'master.dpapi'))
    parser.add_argument('--identity')
    parser.add_argument('--known-hosts')
    parser.add_argument('--target')
    parser.add_argument('--backup-file')
    args = parser.parse_args()
    try:
        if os.name != 'nt':
            raise BackupRejected('This production CLI requires Windows DPAPI.')
        key_path = safe_path(args.key_file)
        destination = safe_path(args.destination)
        if destination == key_path.parent or destination in key_path.parents or key_path.parent in destination.parents:
            raise BackupRejected('Keep the protected master key separate from backups.')
        master = master_key(key_path, create=args.action == 'backup')
        if args.action == 'drill':
            if not args.backup_file:
                raise BackupRejected('Choose an encrypted backup file.')
            path = safe_path(args.backup_file)
            if not path.is_file() or path.stat().st_size > MAX_ENVELOPE:
                raise BackupRejected('Backup missing or above limit.')
            report = drill_backup(path.read_bytes(), master)
        else:
            if not all((args.identity, args.known_hosts, args.target)):
                raise BackupRejected('Pinned private SSH access is required.')
            destination.mkdir(parents=True, exist_ok=True)
            safe_path(destination)
            restrict_permissions(destination, True)
            session = secrets.token_bytes(32)
            remote = fetch_remote(args.identity, args.known_hosts, args.target, session)
            wrapped = wrap_remote(remote, session, master)
            # A failed drill never promotes an invalid archive to a saved backup.
            report = drill_backup(wrapped, master)
            name = 'clipbot-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-'+secrets.token_hex(4)+'.cbk'
            atomic_write(destination/name, wrapped)
            report.update(backupSaved=True, backupFile=name, encryptedBytes=len(wrapped))
        print(json.dumps(report, sort_keys=True))
        return 0
    except Exception:
        print('Encrypted backup operation failed safely; no backup promoted.', file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
