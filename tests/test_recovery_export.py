import os
import pytest
from ops.recovery_export import seal_recovery,open_recovery
from ops.encrypted_backup import BackupRejected

SECRET='A separate offline passphrase! 2026'


def test_portable_export_hides_master_and_authenticates_every_byte():
    key=os.urandom(32);blob=seal_recovery(key,SECRET)
    assert key not in blob and SECRET.encode() not in blob
    assert open_recovery(blob,SECRET)==key
    assert seal_recovery(key,SECRET)!=blob
    for invalid in [blob[:-1],blob[:-1]+bytes([blob[-1]^1]),b'bad',blob+b'extra']:
        with pytest.raises(BackupRejected):open_recovery(invalid,SECRET)
    with pytest.raises(BackupRejected):open_recovery(blob,SECRET+'wrong')


@pytest.mark.parametrize('secret',['short','x'*1025,'a'*20+'\n'])
def test_unreasonable_unlock_input_rejected(secret):
    with pytest.raises(BackupRejected):seal_recovery(os.urandom(32),secret)


def test_wrong_master_key_size_rejected():
    with pytest.raises(BackupRejected):seal_recovery(b'bad',SECRET)
