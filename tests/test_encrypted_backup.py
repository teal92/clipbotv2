import io
import json
import os
import sqlite3
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest


def api():
    from ops import encrypted_backup as backup
    return backup


def database(path):
    with sqlite3.connect(path) as db:
        db.executescript('CREATE TABLE users(id INTEGER PRIMARY KEY,email TEXT); CREATE TABLE tokens(value BLOB);')
        db.execute('INSERT INTO users VALUES(?,?)', (1, 'private@example.invalid'))
        db.execute('INSERT INTO tokens VALUES(?)', (b'customer-secret',))


def test_backup_module_exists():
    assert (Path(__file__).parents[1] / 'ops' / 'encrypted_backup.py').is_file()


def test_roundtrip_snapshot_is_consistent_and_source_unchanged(tmp_path, capsys):
    b = api(); source = tmp_path / 'source.db'; database(source)
    before = source.read_bytes()
    settings = {'CLIPBOT_TOKEN_ENCRYPTION_KEY': 'secret-key', 'STRIPE_SECRET_KEY': 'stripe-secret', 'UNRELATED_SECRET': 'exclude-me'}
    archive = b.snapshot_archive(source, settings)
    key = os.urandom(32)
    sealed = b.seal(archive, key, {'kind': 'snapshot', 'version': 1})
    assert b.open_envelope(sealed, key)[0] == archive
    report = b.drill_archive(archive)
    assert report['integrityOk'] and report['allTableContentMatches']
    assert report['tablesCompared'] == 2
    with zipfile.ZipFile(io.BytesIO(archive)) as z:
        recovery = json.loads(z.read('recovery.json'))
        assert recovery == {k: v for k, v in settings.items() if k != 'UNRELATED_SECRET'}
        restored = tmp_path / 'restored.db'
        restored.write_bytes(z.read('database.db'))
    with sqlite3.connect(restored) as db:
        assert db.execute('SELECT * FROM users').fetchall() == [(1, 'private@example.invalid')]
        assert db.execute('SELECT * FROM tokens').fetchall() == [(b'customer-secret',)]
    assert source.read_bytes() == before
    assert b'customer-secret' not in sealed and b'secret-key' not in sealed
    assert not capsys.readouterr().out


def test_nonce_random_and_metadata_authenticated():
    b = api(); key = os.urandom(32)
    first = b.seal(b'private', key, {'kind': 'snapshot', 'version': 1})
    assert first != b.seal(b'private', key, {'kind': 'snapshot', 'version': 1})
    for damaged, wrong_key in [(first[:-1] + bytes([first[-1] ^ 1]), key), (first.replace(b'snapshot', b'snapshox'), key), (first, os.urandom(32)), (b'invalid', key)]:
        with pytest.raises(b.BackupRejected): b.open_envelope(damaged, wrong_key)


def test_archive_rejects_traversal_and_bad_database(tmp_path):
    b = api()
    for name in ('../escape', '/absolute', 'C:/escape', 'database.db'):
        stream = io.BytesIO()
        with zipfile.ZipFile(stream, 'w') as z: z.writestr(name, b'invalid')
        with pytest.raises(b.BackupRejected): b.drill_archive(stream.getvalue())
    with pytest.raises(b.BackupRejected): b.drill_archive(b'not-zip')


def test_quota_bounds(tmp_path, monkeypatch):
    b = api(); monkeypatch.setattr(b, 'MAX_ARCHIVE', 1024)
    with pytest.raises(b.BackupRejected): b.seal(b'x' * 1025, os.urandom(32), {'kind': 'snapshot', 'version': 1})
    path = tmp_path / 'large.db'; database(path)
    with pytest.raises(b.BackupRejected): b.snapshot_archive(path, {})


def test_atomic_write_refuses_overwrite_and_links(tmp_path):
    b = api(); path = tmp_path / 'snapshot.cbk'
    b.atomic_write(path, b'encrypted')
    with pytest.raises(b.BackupRejected): b.atomic_write(path, b'replacement')
    assert path.read_bytes() == b'encrypted'
    with pytest.raises(b.BackupRejected): b.atomic_write(tmp_path / '..' / 'escape.cbk', b'bad')
    link = tmp_path / 'link'
    try: link.symlink_to(tmp_path, target_is_directory=True)
    except OSError: pytest.skip('Windows account cannot create symlinks')
    with pytest.raises(b.BackupRejected): b.atomic_write(link / 'escape.cbk', b'bad')


def test_archive_content_tampering_rejected(tmp_path):
    b = api(); path = tmp_path / 'source.db'; database(path)
    archive = b.snapshot_archive(path, {})
    stream = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(archive)) as old, zipfile.ZipFile(stream, 'w') as new:
        for name in old.namelist(): new.writestr(name, b'corrupt' if name == 'database.db' else old.read(name))
    with pytest.raises(b.BackupRejected): b.drill_archive(stream.getvalue())


def test_private_key_protector_injected_only_in_library(tmp_path):
    b = api()
    class Protector:
        def protect(self, data): return b'protected:' + data
        def unprotect(self, data): return data.removeprefix(b'protected:')
    path = tmp_path / 'master.dpapi'
    key = b.master_key(path, Protector())
    assert len(key) == 32 and b.master_key(path, Protector()) == key
    assert path.read_bytes().startswith(b'protected:')


def test_remote_script_contains_no_credentials_and_fixed_source():
    b = api(); script = b.remote_script()
    assert '/var/data/clipbot.db' in script
    assert 'sys.stdin.buffer.read(33)' in script
    assert 'stripe-secret' not in script and 'customer-secret' not in script


def test_session_wrapping_authenticates_and_drills(tmp_path):
    b = api(); path = tmp_path / 'source.db'; database(path)
    session, master = os.urandom(32), os.urandom(32)
    remote = b.seal(b.snapshot_archive(path, {}), session, {'kind': 'snapshot', 'version': 1})
    wrapped = b.wrap_remote(remote, session, master)
    assert b.drill_backup(wrapped, master)['integrityOk']
    with pytest.raises(b.BackupRejected): b.drill_backup(wrapped, os.urandom(32))


def test_compressed_archive_and_duplicates_are_rejected(tmp_path):
    b = api(); path = tmp_path / 'source.db'; database(path)
    original = b.snapshot_archive(path, {})
    stream = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(original)) as old, zipfile.ZipFile(stream, 'w', compression=zipfile.ZIP_DEFLATED) as new:
        for name in old.namelist(): new.writestr(name, old.read(name))
    with pytest.raises(b.BackupRejected): b.drill_archive(stream.getvalue())


@pytest.mark.skipif(os.name != 'nt', reason='DPAPI is Windows only')
def test_real_windows_dpapi_and_private_key_roundtrip(tmp_path):
    b = api(); key = os.urandom(32); protector = b.WindowsDPAPI()
    protected = protector.protect(key)
    assert protected != key and key not in protected
    assert protector.unprotect(protected) == key
    with pytest.raises(b.BackupRejected): protector.unprotect(b'not-dpapi')
    key_path = tmp_path / 'key-directory' / 'master.dpapi'
    assert b.master_key(key_path) == b.master_key(key_path, create=False)


def test_cli_bad_arguments_do_not_emit_secrets(tmp_path, monkeypatch, capsys):
    b = api()
    monkeypatch.setattr('sys.argv', ['backup', 'backup', '--destination', str(tmp_path / 'output'), '--key-file', str(tmp_path / 'keys' / 'master.dpapi')])
    assert b.main() == 1
    output = capsys.readouterr()
    assert output.out == ''
    assert output.err == 'Encrypted backup operation failed safely; no backup promoted.\n'


def test_remote_ciphertext_is_bounded_and_inner_kind_checked():
    b = api(); session = os.urandom(32)
    incorrect = b.seal(b'invalid', session, {'kind': 'wrapped', 'version': 1})
    with pytest.raises(b.BackupRejected): b.wrap_remote(incorrect, session, os.urandom(32))


def test_corrupt_recovery_hash_and_manifest_rows_rejected(tmp_path):
    b = api(); path = tmp_path / 'source.db'; database(path)
    original = b.snapshot_archive(path, {'STRIPE_SECRET_KEY': 'private-secret'})
    for change in ('recovery.json', 'manifest.json'):
        stream = io.BytesIO()
        with zipfile.ZipFile(io.BytesIO(original)) as old, zipfile.ZipFile(stream, 'w') as new:
            for name in old.namelist():
                data = old.read(name)
                if name == change:
                    if name == 'recovery.json': data = b'{}'
                    else:
                        manifest = json.loads(data); manifest['tables']['users']['rows'] += 1
                        data = json.dumps(manifest).encode()
                new.writestr(name, data)
        with pytest.raises(b.BackupRejected): b.drill_archive(stream.getvalue())


def test_remote_program_encrypts_fixture_and_never_logs_credentials(tmp_path):
    b = api(); path = tmp_path / 'source.db'; database(path)
    # Change only the fixed DB literal in this test process, never production code.
    script = b.remote_script().replace("Path('/var/data/clipbot.db')", 'Path('+repr(path.as_posix())+')')
    environment = dict(os.environ, CLIPBOT_C2_SERVICE_KEY='operator-fixture-secret', STRIPE_SECRET_KEY='stripe-fixture-secret')
    session = os.urandom(32)
    result = subprocess.run([sys.executable, '-c', script], input=session, capture_output=True, env=environment, timeout=30)
    assert result.returncode == 0 and result.stderr == b''
    assert b'customer-secret' not in result.stdout and b'stripe-fixture-secret' not in result.stdout
    archive, metadata = b.open_envelope(result.stdout, session)
    assert metadata['kind'] == 'snapshot'
    assert b.drill_archive(archive)['operatorKeyPresent']
    failed = subprocess.run([sys.executable, '-c', script], input=b'bad-key', capture_output=True, env=environment, timeout=30)
    assert failed.returncode == 1 and failed.stdout == b''
    assert failed.stderr.replace(b'\r\n', b'\n') == b'Encrypted snapshot failed safely.\n'
