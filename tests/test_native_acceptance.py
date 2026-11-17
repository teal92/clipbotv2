import hashlib
import importlib

import pytest


def module():
    return importlib.import_module('tools.accept_native_companion')


def test_packaged_acceptance_rejects_changed_or_wrong_target_artifacts(tmp_path):
    artifact=tmp_path/'candidate.dmg'
    artifact.write_bytes(b'candidate')
    receipt={'target':'macos-arm64','sourceCommit':'a'*40,'sizeBytes':9,
             'sha256':hashlib.sha256(artifact.read_bytes()).hexdigest(),'channel':'internal'}
    module().check_artifact(artifact,receipt,'macos-arm64','a'*40)
    for target,source in [('macos-x86_64','a'*40),('macos-arm64','b'*40)]:
        with pytest.raises(ValueError):
            module().check_artifact(artifact,receipt,target,source)
    artifact.write_bytes(b'alteredxx')
    with pytest.raises(ValueError):
        module().check_artifact(artifact,receipt,'macos-arm64','a'*40)


def test_partial_diagnostics_never_pass_packaged_acceptance():
    check=module().check_diagnostics
    with pytest.raises(ValueError):
        check({'modelLoads':True})
    required=('ffmpeg','ffprobe','captureInstalled','transcriptionInstalled','metricsInstalled',
              'modelDownloaded','modelLoads','mediaTranscribes','rollingClipPasses',
              'candidatePreviewPasses','verticalReviewPasses')
    values=dict.fromkeys(required,True)
    assert check(values) is None
    values['rollingClipPasses']=False
    with pytest.raises(ValueError):
        check(values)


def test_native_acceptance_requires_matching_host_before_writing_report(tmp_path):
    with pytest.raises(ValueError,match='matching native'):
        module().accept('macos-arm64',tmp_path/'app.dmg',tmp_path/'receipt.json',tmp_path/'report.json',host_target='windows-x86_64')
    assert not (tmp_path/'report.json').exists()


def test_synthetic_media_uses_file_inputs_without_device_capture_features(tmp_path):
    import wave
    video,audio=module().synthetic_sources(tmp_path,seconds=1)
    assert video.read_bytes().startswith(b'YUV4MPEG2 W320 H180 F5:1 Ip A1:1 C420jpeg\nFRAME\n')
    with wave.open(str(audio),'rb') as recording:
        assert recording.getframerate()==16000 and recording.getnframes()==16000
    command=module().synthetic_arguments(tmp_path/'ffmpeg',video,audio,tmp_path/'probe.mp4',seconds=1)
    assert 'lavfi' not in command
    assert str(video) in command and str(audio) in command
    assert command[command.index('-g')+1]=='25'
    for duration in (0,81,1.5):
        with pytest.raises(ValueError):
            module().synthetic_sources(tmp_path,seconds=duration)
