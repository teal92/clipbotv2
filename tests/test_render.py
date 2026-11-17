from pathlib import Path
import json,shutil,subprocess
import pytest
from worker.render import render,ass_text,RenderError

def test_subtitles_treat_transcript_as_text():
    text=ass_text([{'start':0,'end':20,'text':r'{\pos(1,1)}hello'}],0,15)
    assert r'{\pos' not in text and 'hello' in text
    assert '0:00:15.00' in text

def test_render_rejects_unsafe_ranges(tmp_path):
    with pytest.raises(RenderError):render({'start':-1,'end':50},tmp_path/'absent.mkv',[],tmp_path)

@pytest.mark.skipif(not shutil.which('ffmpeg'),reason='Local encoding integration requires FFmpeg')
def test_real_renderer_has_verified_vertical_video_audio_and_subtitles(tmp_path):
    source=tmp_path/'capture.mkv'
    subprocess.run(['ffmpeg','-nostdin','-v','error','-y','-f','lavfi','-i','testsrc2=size=320x180:rate=5','-f','lavfi','-i','sine=frequency=440','-t','15','-c:v','libx264','-preset','ultrafast','-c:a','aac',str(source)],check=True,timeout=30)
    artifact=render({'start':0,'end':15},source,[{'start':0,'end':3,'text':'Local renderer test'}],tmp_path)
    data=json.loads(subprocess.run(['ffprobe','-v','error','-show_streams','-show_format','-of','json',str(artifact['path'])],capture_output=True,text=True,check=True,timeout=15).stdout)
    video=next(s for s in data['streams'] if s['codec_type']=='video')
    assert (video['width'],video['height'],video['codec_name'])==(1080,1920,'h264')
    assert any(s['codec_name']=='aac' for s in data['streams'])
    assert 14.8<float(data['format']['duration'])<15.5
    assert artifact['sizeBytes']>0 and len(artifact['sha256'])==64


def test_vertical_review_preserves_landscape_and_blurs_background(tmp_path,monkeypatch):
    source=tmp_path/'capture.mkv';source.write_bytes(b'media');calls=[]
    def run(args,**kwargs):
        calls.append(args)
        if args[0]=='ffmpeg':
            Path(args[-1]).write_bytes(b'rendered')
            return type('Result',(),{'returncode':0})()
        return type('Result',(),{'returncode':0,'stdout':json.dumps({'streams':[{'codec_type':'video','width':1080,'height':1920,'codec_name':'h264'},{'codec_type':'audio','codec_name':'aac'}],'format':{'duration':'20'}})})()
    monkeypatch.setattr(subprocess,'run',run)
    artifact=render({'start':0,'end':20},source,[{'start':0,'end':3,'text':'We own the future'}],tmp_path)
    graph=calls[0][calls[0].index('-filter_complex')+1]
    assert 'boxblur' in graph and 'force_original_aspect_ratio=decrease' in graph and 'overlay' in graph and 'subtitles=subtitles.ass' in graph
    assert artifact['framing']=='blurred_fit' and artifact['path'].name=='clip.mp4'
    assert 'We own the future' in (tmp_path/'subtitles.ass').read_text(encoding='utf-8')
