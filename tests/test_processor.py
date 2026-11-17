import threading
from types import SimpleNamespace as NS
from unittest.mock import Mock
from worker.processor import ClipProcessor


def test_cancelled_render_never_registers_preview_or_reports_ready(tmp_path,monkeypatch):
    monkeypatch.setattr('worker.processor.load_model',lambda _:None)
    client=Mock();previews={};processor=ClipProcessor(client,tmp_path,tmp_path,previews)
    event=threading.Event();job={'id':'a'*32,'lease':'b'*32}
    processor.entries[job['id']]={'job':job,'path':tmp_path/'capture.mkv','event':event,'candidate':{},'transcript':[],'phase':'rendering'}
    def finish(*args,**kwargs):event.set();return {'path':tmp_path/'clip.mp4'}
    monkeypatch.setattr('worker.processor.render',finish)
    try:processor._render(job['id']);assert previews=={};client.request.assert_not_called()
    finally:processor.close()


def test_restart_restores_only_server_owned_verified_preview(tmp_path,monkeypatch):
    import hashlib
    monkeypatch.setattr('worker.processor.load_model',lambda _:None)
    owned='a'*32;foreign='c'*32
    for identity in (owned,foreign):
        directory=tmp_path/identity;directory.mkdir();(directory/'clip.mp4').write_bytes(b'unit-artifact')
    metadata={'sha256':hashlib.sha256(b'unit-artifact').hexdigest(),'sizeBytes':13,'previewToken':'b'*64}
    client=Mock();client.request.return_value={'jobs':[{'id':owned,'stage':'ready','source':{'platform':'twitch','login':'one'},'artifact':metadata,'candidate':None,'leaseExpires':0}], 'publications':[]}
    previews={};processor=ClipProcessor(client,tmp_path,tmp_path,previews)
    try:
        processor.tick()
        assert set(previews)=={'b'*64}
        assert set(processor.entries)=={owned}
        assert previews['b'*64]==(tmp_path/owned/'clip.mp4').resolve()
    finally:processor.close()


def test_decoder_incompatibility_reports_safe_reason_without_paid_analysis(tmp_path,monkeypatch):
    monkeypatch.setattr('worker.processor.load_model',lambda _:None)
    def fail(*args,**kwargs):raise TypeError("open() got an unexpected keyword argument 'metadata_errors'")
    monkeypatch.setattr('worker.processor.transcribe',fail)
    monkeypatch.setattr('worker.processor.probe',lambda _:40)
    client=Mock();processor=ClipProcessor(client,tmp_path,tmp_path,{})
    job={'id':'a'*32,'lease':'b'*32}
    processor.pending.acquire()
    processor.entries[job['id']]={'job':job,'path':tmp_path/'capture.mkv','event':threading.Event(),'phase':'transcribing'}
    try:
        processor._analyze(job['id'])
        client.request.assert_not_called()
        client.report.assert_called_once_with(job,{'stage':'failed','errorCode':'dependency_mismatch'})
    finally:processor.close()
