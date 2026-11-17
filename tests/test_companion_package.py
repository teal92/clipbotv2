from pathlib import Path
from packaging_audit import audit_bundle

def test_bundle_audit_rejects_credentials_and_customer_media(tmp_path):
 (tmp_path/'.env').write_text('private');(tmp_path/'capture.mkv').write_bytes(b'private')
 errors=audit_bundle(tmp_path)
 assert any('.env' in v for v in errors) and any('capture.mkv' in v for v in errors)


def test_bundle_audit_rejects_edited_clips_recovery_and_personal_memory(tmp_path):
 for name in ['clip-edit-'+'a'*32+'.mp4','artifact-recovery.json','candidate.json','device.bin','private.cbk','signing.pfx','job.json']:
  (tmp_path/name).write_bytes(b'private')
 memory=tmp_path/'personal-memory';memory.mkdir();(memory/'feedback.json').write_text('{}')
 errors=audit_bundle(tmp_path)
 assert len(errors)>=8


def test_bundle_audit_rejects_missing_or_empty_bundle(tmp_path):
 assert audit_bundle(tmp_path/'missing')
 assert audit_bundle(tmp_path)


def test_model_and_public_notices_are_not_mistaken_for_customer_files(tmp_path):
 (tmp_path/'model.bin').write_bytes(b'model');(tmp_path/'cacert.pem').write_text('public trust roots')
 assert audit_bundle(tmp_path)==[]


def test_installer_upgrade_can_clear_previously_enabled_startup():
    recipe=(Path(__file__).parents[1]/'packaging/clipbot-companion.iss').read_text(encoding='utf-8')
    entries=[line for line in recipe.splitlines() if 'CurrentVersion\\Run' in line and 'ValueName: "ClipBotCompanion"' in line]
    assert len(entries)==2
    assert 'ValueType: none' in entries[0] and 'deletevalue' in entries[0].split('Flags: ')[1].split()
    assert 'Tasks:' not in entries[0]
    assert 'Tasks: startup' in entries[1] and 'ValueType: string' in entries[1]
    assert all('Root: HKCU;' in line and 'uninsdeletevalue' in line for line in entries)
