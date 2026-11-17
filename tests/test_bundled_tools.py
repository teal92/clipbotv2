import json,sys
from types import SimpleNamespace
from pathlib import Path
import pytest
from worker.capture import probe


def frozen(monkeypatch,tmp_path):
    bundle=tmp_path/'installed';(bundle/'bin').mkdir(parents=True)
    monkeypatch.setattr(sys,'frozen',True,raising=False)
    monkeypatch.setattr(sys,'_MEIPASS',str(bundle),raising=False)
    return bundle


def test_frozen_probe_uses_exact_bundled_executable_not_working_directory(monkeypatch,tmp_path):
    bundle=frozen(monkeypatch,tmp_path)
    tool=bundle/'bin'/('ffprobe.exe' if sys.platform=='win32' else 'ffprobe');tool.write_bytes(b'fixture-not-executed')
    calls=[]
    def run(args,**kwargs):
        calls.append(args)
        return SimpleNamespace(returncode=0,stdout=json.dumps({'format':{'duration':'20'},'streams':[{'codec_type':'video'}]}))
    monkeypatch.setattr('subprocess.run',run)
    assert probe(tmp_path/'capture.mkv')==20
    assert Path(calls[0][0])==tool.resolve()


def test_frozen_missing_media_tool_never_falls_back_to_path(monkeypatch,tmp_path):
    frozen(monkeypatch,tmp_path)
    calls=[]
    monkeypatch.setattr('subprocess.run',lambda *a,**k:calls.append(a))
    with pytest.raises(RuntimeError,match='bundled'):
        probe(tmp_path/'capture.mkv')
    assert not calls


def test_frozen_readiness_requires_bundled_downloader_even_if_module_exists(monkeypatch,tmp_path):
    bundle=frozen(monkeypatch,tmp_path)
    for name in ('ffmpeg','ffprobe'):(bundle/'bin'/(name+('.exe' if sys.platform=='win32' else ''))).write_bytes(b'fixture')
    from worker.prerequisites import prerequisites
    assert prerequisites()['captureInstalled'] is False


def test_downloader_cannot_load_unreviewed_plugins_runtimes_or_remote_components(monkeypatch):
    from worker.capture import resolve
    calls=[]
    def run(args,**kwargs):
        calls.append(args)
        return SimpleNamespace(returncode=0,stdout='https://abc.ttvnw.net/live.m3u8\n')
    monkeypatch.setattr('subprocess.run',run)
    assert resolve({'platform':'twitch','login':'channel'}).startswith('https://abc.ttvnw.net/')
    for option in ('--ignore-config','--no-plugin-dirs','--no-remote-components','--no-js-runtimes'):
        assert option in calls[0]
