import importlib
import os
import sys
import time

import pytest


def test_launch_arguments_accept_one_application_url_and_reject_conflicts():
    module = importlib.import_module('worker.companion')
    args, code = module.parse_launch_args(['clipbot-companion://pair?code=' + 'a' * 24])
    assert code == 'a' * 24
    assert args.background is False
    args, code = module.parse_launch_args(['--handoff', 'clipbot-companion://pair?code=' + 'a' * 24, 'clipbot-companion://pair?code=' + 'b' * 24])
    assert args.invalid_link and code is None


def test_invalid_pairing_link_never_raises_or_exits_and_main_returns_cleanly(monkeypatch):
    module = importlib.import_module('worker.companion')
    shown = []
    monkeypatch.setattr(module, 'show_invalid_link', lambda: shown.append(True))
    for bad in ['clipbot-companion://pair?code=x', 'https://evil.test/', 'clipbot-companion://pair', '']:
        args, code = module.parse_launch_args([bad])
        assert code is None and (args.invalid_link or bad == '')
    monkeypatch.setattr(sys, 'argv', ['companion', 'clipbot-companion://pair?code=short'])
    module.main()
    assert shown == [True]


def test_consumed_handoff_is_one_time_and_stale_handoff_is_deleted(tmp_path, monkeypatch):
    from worker.platforms.posix_integration import consume_pair_link
    from worker import credentials
    path = tmp_path / 'pair-handoff.bin'
    path.write_bytes(b'opaque')
    monkeypatch.setattr(credentials, 'load', lambda *args: 'a' * 24)
    monkeypatch.setattr(credentials, 'delete', lambda p, origin: p.unlink())
    assert consume_pair_link(tmp_path) == 'a' * 24
    assert consume_pair_link(tmp_path) is None
    path.write_bytes(b'opaque')
    os.utime(path, (time.time() - 601, time.time() - 601))
    assert consume_pair_link(tmp_path) is None
    assert not path.exists()


def test_pairing_cannot_succeed_with_memory_only_fallback(tmp_path, monkeypatch):
    from fastapi import HTTPException
    from worker.local_app import create_local_app
    class Client:
        def __init__(self, *args):
            self.token = None
        def close(self):
            pass
        def connect(self, code):
            self.token = 'private-device-token-' + 'a' * 24
        def heartbeat(self):
            return {}
    def unavailable(*args):
        raise RuntimeError('private-device-token-' + 'a' * 24)
    monkeypatch.setattr('worker.local_app.WorkerClient', Client)
    monkeypatch.setattr('worker.credentials.save', unavailable)
    app = create_local_app('https://clipbot.example', tmp_path, start_runtime=False)
    with pytest.raises(HTTPException) as error:
        app.state.pair_companion('a' * 24)
    assert error.value.status_code == 409
    assert 'private-device-token' not in str(error.value.detail)
    assert app.state.worker['client'].token is None


def test_handoff_accepts_small_filesystem_clock_skew_but_not_future_codes(tmp_path, monkeypatch):
    from worker.platforms.posix_integration import consume_pair_link
    path = tmp_path / 'pair-handoff.bin'
    monkeypatch.setattr('worker.platforms.posix_integration.time.time', lambda: 2000)
    monkeypatch.setattr('worker.credentials.load', lambda *args: 'a' * 24)
    monkeypatch.setattr('worker.credentials.delete', lambda p, origin: p.unlink())
    path.write_bytes(b'opaque')
    os.utime(path, (2000.25, 2000.25))
    assert consume_pair_link(tmp_path) == 'a' * 24
    path.write_bytes(b'opaque')
    os.utime(path, (2060, 2060))
    assert consume_pair_link(tmp_path) is None
    assert not path.exists()


@pytest.mark.skipif(os.name == 'nt', reason='native POSIX link ownership test')
def test_handoff_symlink_cannot_delete_another_file(tmp_path):
    from worker.platforms.posix_integration import consume_pair_link
    outside = tmp_path / 'other-file'
    outside.write_bytes(b'protected')
    (tmp_path / 'pair-handoff.bin').symlink_to(outside)
    with pytest.raises(RuntimeError):
        consume_pair_link(tmp_path)
    assert outside.read_bytes() == b'protected'
