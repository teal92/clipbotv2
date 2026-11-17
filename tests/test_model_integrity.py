import hashlib,sys
from types import SimpleNamespace
import pytest
from worker.model_integrity import verify_model,MODEL_FILES


def test_model_pins_cover_only_expected_snapshot_files():
    assert set(MODEL_FILES)=={'config.json','model.bin','tokenizer.json','vocabulary.txt'}
    assert all(len(value)==64 for value in MODEL_FILES.values())


def test_modified_model_rejected_before_runtime_import(tmp_path,monkeypatch):
    (tmp_path/'model.bin').write_bytes(b'untrusted')
    def forbidden(*args,**kwargs):pytest.fail('Unverified model must not be loaded')
    monkeypatch.setitem(sys.modules,'faster_whisper',SimpleNamespace(WhisperModel=forbidden))
    from worker.transcribe import load_model,TranscriptionError
    with pytest.raises(TranscriptionError,match='integrity'):load_model(tmp_path)


def test_verified_model_then_tamper_fails(tmp_path,monkeypatch):
    import worker.model_integrity as module
    digest=hashlib.sha256(b'fixture').hexdigest();monkeypatch.setattr(module,'MODEL_FILES',{'model.bin':digest})
    (tmp_path/'model.bin').write_bytes(b'fixture');assert verify_model(tmp_path) is None
    (tmp_path/'model.bin').write_bytes(b'tampered')
    with pytest.raises(ValueError):verify_model(tmp_path)


def test_unverified_loader_config_is_rejected_even_when_four_pins_match(tmp_path,monkeypatch):
    import worker.model_integrity as module
    digest=hashlib.sha256(b'fixture').hexdigest();monkeypatch.setattr(module,'MODEL_FILES',{'model.bin':digest})
    (tmp_path/'model.bin').write_bytes(b'fixture')
    (tmp_path/'preprocessor_config.json').write_text('{"n_fft":999999999}')
    with pytest.raises(ValueError,match='integrity'):verify_model(tmp_path)
