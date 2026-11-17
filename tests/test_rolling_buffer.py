from pathlib import Path
from threading import Event
from worker.rolling_buffer import RollingBuffer,selected_parts,extract
from worker.capture import CaptureError
import pytest

def test_clip_parts_cover_before_and_after_without_extra_segments():
 parts=[(Path(str(i)),i*5,(i+1)*5) for i in range(20)]
 assert [p[0].name for p in selected_parts(parts,20,60)]==[str(i) for i in range(4,12)]

def test_trigger_waits_for_prebuffer_and_rejects_duplicate(tmp_path):
 b=RollingBuffer({'platform':'kick','login':'channel'},tmp_path,Event(),lambda p:None,lambda *a:None,lambda s:None)
 assert not b.trigger(20,20,{})
 b.parts=[(tmp_path/'segment-00000000.mkv',0,30)];b.media_time=30
 assert b.trigger(20,20,{'id':'test'})
 assert not b.trigger(20,20,{'id':'duplicate'})

def test_extraction_rejects_missing_requested_footage(tmp_path):
 with pytest.raises(CaptureError):extract([],20,60,tmp_path,Event())
 with pytest.raises(CaptureError):extract([(tmp_path/'a',5,30)],0,30,tmp_path,Event())


def test_delayed_speech_trigger_keeps_segment_timestamp(tmp_path):
 b=RollingBuffer({'platform':'kick','login':'channel'},tmp_path,Event(),lambda p:None,lambda *a:None,lambda s:None)
 b.parts=[(tmp_path/'segment-00000000.mkv',0,80)];b.media_time=80
 assert b.trigger(20,20,{'id':'speech'},position=40)
 assert b.pending[:2]==(20,60)
