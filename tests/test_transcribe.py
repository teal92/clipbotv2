from types import SimpleNamespace as NS
import pytest
from worker.transcribe import transcribe,TranscriptionError

def test_transcription_is_local_timestamped_and_bounded(tmp_path):
    media=tmp_path/'live.mkv';media.write_bytes(b'test')
    class Model:
        def transcribe(self,path,**kwargs):return iter([NS(start=0,end=2,text=' hello ')]),None
    assert transcribe(media,Model())==[{'start':0.0,'end':2.0,'text':'hello'}]
    class Bad:
        def transcribe(self,*a,**k):return iter([NS(start=-1,end=999,text='bad')]),None
    with pytest.raises(TranscriptionError):transcribe(media,Bad())

@pytest.mark.parametrize('end,accepted',[(60.4,True),(61.01,False),(999,False)])
def test_transcript_is_bounded_by_actual_media(tmp_path,end,accepted):
    class Model:
        def transcribe(self,*args,**kwargs):return iter([NS(start=58,end=end,text='final words')]),None
    if accepted:assert transcribe(tmp_path/'media.mkv',Model(),duration=60)[0]['end']==60
    else:
        with pytest.raises(TranscriptionError):transcribe(tmp_path/'media.mkv',Model(),duration=60)
