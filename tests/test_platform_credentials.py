import importlib
import sys

import pytest

from worker import credentials


class MemoryVault:
    """Boundary substitute for unavailable native desktop keyrings."""
    def __init__(self):
        self.entries = {}

    def put(self, key, value):
        self.entries[key] = value

    def get(self, key):
        return self.entries.get(key)

    def remove(self, key):
        self.entries.pop(key, None)


@pytest.fixture
def native(monkeypatch):
    storage = importlib.import_module('worker.platforms.secrets')
    vault = MemoryVault()
    monkeypatch.setattr(sys, 'platform', 'darwin')
    monkeypatch.setattr(storage, 'backend', lambda: vault)
    return vault


def test_native_credentials_isolate_origin_and_handoff(native, tmp_path):
    device, handoff = tmp_path / 'device.bin', tmp_path / 'pair-handoff.bin'
    credentials.save(device, 'https://clipbot.your-domain.example', 'device-token-' + 'a' * 24)
    credentials.save(handoff, 'https://clipbot.your-domain.example', 'pair-code-' + 'b' * 24)
    assert credentials.load(device, 'https://clipbot.your-domain.example') == 'device-token-' + 'a' * 24
    assert credentials.load(handoff, 'https://clipbot.your-domain.example') == 'pair-code-' + 'b' * 24
    assert credentials.load(device, 'https://other.example') is None
    assert b'device-token' not in device.read_bytes()
    assert b'pair-code' not in handoff.read_bytes()
    credentials.delete(handoff, 'https://clipbot.your-domain.example')
    assert not handoff.exists()
    assert credentials.load(handoff, 'https://clipbot.your-domain.example') is None
    assert credentials.load(device, 'https://clipbot.your-domain.example') == 'device-token-' + 'a' * 24


def test_native_storage_failure_has_no_plaintext_fallback(native, tmp_path):
    def locked(*args):
        raise RuntimeError('backend detail containing private-token-' + 'x' * 24)
    native.put = locked
    path = tmp_path / 'device.bin'
    with pytest.raises(RuntimeError) as error:
        credentials.save(path, 'https://clipbot.your-domain.example', 'private-token-' + 'x' * 24)
    assert 'private-token' not in str(error.value)
    assert not path.exists()
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize('token', ['', 'short', 'a' * 101, None])
def test_bad_token_never_persisted(native, tmp_path, token):
    with pytest.raises(ValueError):
        credentials.save(tmp_path / 'device.bin', 'https://clipbot.your-domain.example', token)
    assert list(tmp_path.iterdir()) == []


def test_corrupt_marker_cannot_load_native_secret(native, tmp_path):
    path = tmp_path / 'device.bin'
    credentials.save(path, 'https://clipbot.your-domain.example', 'a' * 24)
    path.write_bytes(b'corrupted')
    assert credentials.load(path, 'https://clipbot.your-domain.example') is None


def test_locked_native_keyring_reports_actionable_error_without_secret(native, tmp_path):
    path = tmp_path / 'device.bin'
    credentials.save(path, 'https://clipbot.your-domain.example', 'a' * 24)
    def locked(*args):
        raise RuntimeError('secret-backend-details-' + 'a' * 24)
    native.get = locked
    with pytest.raises(RuntimeError, match='[Uu]nlock') as error:
        credentials.load(path, 'https://clipbot.your-domain.example')
    assert 'secret-backend-details' not in str(error.value)


@pytest.mark.skipif(sys.platform not in ('darwin', 'linux'), reason='native desktop keyring required')
def test_real_native_keyring_roundtrip(tmp_path):
    path = tmp_path / 'test-device.bin'
    try:
        credentials.save(path, 'https://clipbot.your-domain.example', 'native-check-' + 'a' * 24)
        assert credentials.load(path, 'https://clipbot.your-domain.example') == 'native-check-' + 'a' * 24
    finally:
        credentials.delete(path, 'https://clipbot.your-domain.example')
