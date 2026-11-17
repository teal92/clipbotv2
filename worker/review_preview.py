"""Bounded local review playback, before approval, without vertical editing or AI."""
from .tools import media_tool
import json,math,subprocess,time
from pathlib import Path

def review_preview(candidate,media_path,event):
    start,end=candidate.get('start'),candidate.get('end')
    if any(type(v) not in (int,float) or not math.isfinite(v) for v in (start,end)) or not 0<=start<end<=305 or not 15<=end-start<=60:raise ValueError('Invalid preview range.')
    source=Path(media_path).resolve();directory=source.parent
    if source.name!='capture.mkv' or not source.is_file():raise ValueError('Preview source is unavailable.')
    output=directory/'candidate-preview.mp4';temporary=directory/'candidate-preview.partial.mp4'
    if event.is_set():raise ValueError('Preview cancelled.')
    args=[media_tool('ffmpeg'),'-nostdin','-hide_banner','-loglevel','error','-y','-ss',str(start),'-i',str(source),'-t',str(end-start),'-map','0:v:0','-map','0:a:0','-vf','scale=960:-2,setsar=1','-c:v','libx264','-preset','ultrafast','-crf','26','-threads','2','-c:a','aac','-b:a','96k','-pix_fmt','yuv420p','-movflags','+faststart',str(temporary)]
    process=subprocess.Popen(args,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0));deadline=time.monotonic()+180
    try:
        while process.poll() is None:
            if event.wait(.2) or time.monotonic()>deadline:raise ValueError('Preview cancelled or timed out.')
        if process.returncode or not temporary.is_file():raise ValueError('Local preview could not be prepared.')
        if event.is_set():raise ValueError('Preview cancelled.')
        checked=subprocess.run([media_tool('ffprobe'),'-v','error','-show_streams','-show_format','-of','json',str(temporary)],capture_output=True,text=True,timeout=15,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        try:
            data=json.loads(checked.stdout);duration=float(data['format']['duration']);streams=data['streams']
            if abs(duration-(end-start))>.6 or not any(v.get('codec_type')=='video' and v.get('codec_name')=='h264' for v in streams) or not any(v.get('codec_type')=='audio' and v.get('codec_name')=='aac' for v in streams):raise ValueError()
        except (KeyError,ValueError,TypeError):raise ValueError('Preview media verification failed.') from None
        temporary.replace(output);return output
    finally:
        if process.poll() is None:process.kill();process.wait(timeout=10)
