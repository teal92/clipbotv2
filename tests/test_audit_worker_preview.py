import threading
import pytest
from unittest.mock import Mock
from worker.processor import ClipProcessor

@pytest.mark.parametrize('stage',['failed','cancelled'])
def test_terminal_job_revokes_all_its_previews_but_preserves_other_jobs_and_files(tmp_path,monkeypatch,stage):
    monkeypatch.setattr('worker.processor.load_model',lambda _:None)
    directory=tmp_path/('a'*32);directory.mkdir()
    other=tmp_path/('c'*32);other.mkdir()
    paths=[directory/'clip.mp4',directory/'candidate-preview.mp4',other/'clip.mp4']
    for path in paths:path.write_bytes(b'fixture-media-only')
    previews={('b'*64):paths[0],('d'*64):paths[1],('e'*64):paths[2]}
    client=Mock();client.request.return_value={'jobs':[{'id':'a'*32,'stage':stage}],'publications':[]}
    processor=ClipProcessor(client,tmp_path,tmp_path,previews)
    processor.entries['a'*32]={'job':{'id':'a'*32},'event':threading.Event(),'phase':'ready','path':directory/'capture.mkv'}
    try:
        processor.tick()
        assert set(previews)=={'e'*64}
        assert all(p.is_file() for p in paths)
        assert processor.entries['a'*32]['event'].is_set()
    finally:processor.close()
