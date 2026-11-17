"""Local vertical H.264/AAC rendering with text-only ASS subtitles."""
from .tools import media_tool
import hashlib,json,math,subprocess,re
from pathlib import Path

class RenderError(ValueError):
    def __init__(self,message,code='render_encode_failed'):
        self.code=code;super().__init__(message)

def ass_time(seconds):
    centis=max(0,int(seconds*100));hours,rest=divmod(centis,360000);minutes,rest=divmod(rest,6000);whole,cents=divmod(rest,100)
    return f'{hours}:{minutes:02}:{whole:02}.{cents:02}'

def ass_text(transcript,start,end):
    header='[Script Info]\nScriptType: v4.00+\nPlayResX: 1080\nPlayResY: 1920\nWrapStyle: 0\n[V4+ Styles]\nFormat: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\nStyle: Default,Arial,64,&H00FFFFFF,&H000000FF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,4,1,2,80,80,340,1\n[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n'
    lines=[]
    for s in transcript:
        a=max(start,s['start']);b=min(end,s['end'])
        if a>=b:continue
        text=''.join(c for c in str(s['text']) if ord(c)>=32).replace('\\','ï¼¼').replace('{','(').replace('}',')')
        words=text[:500].split()
        groups=[' '.join(words[i:i+6]) for i in range(0,len(words),6)]
        if len(words)==1 and len(text)>28:groups=[text[i:i+28] for i in range(0,len(text),28)]
        for i,caption in enumerate(groups):
            left=a+(b-a)*i/len(groups);right=a+(b-a)*(i+1)/len(groups)
            lines.append(f'Dialogue: 0,{ass_time(left-start)},{ass_time(right-start)},Default,,0,0,0,,{caption}')
    return header+'\n'.join(lines)+'\n'

def render(candidate,media_path,transcript,output_directory,*,final_name="clip.mp4"):
    if final_name!="clip.mp4" and not re.fullmatch(r"clip-edit-[a-f0-9]{32}\.mp4",final_name):raise RenderError("Invalid render destination.")
    start,end=candidate.get('start'),candidate.get('end')
    if any(type(v) not in (int,float) or not math.isfinite(v) for v in (start,end)) or not 0<=start<end<=305 or not 15<=round(end-start,6)<=60:raise RenderError('Invalid clip range.','render_invalid_range')
    source=Path(media_path).resolve();directory=Path(output_directory).resolve()
    if not source.is_file() or source.parent!=directory:raise RenderError('Clip source must belong to its local job directory.','render_source_unavailable')
    output=directory/'clip.partial.mp4';subs=directory/'subtitles.ass';subs.write_text(ass_text(transcript,start,end),encoding='utf-8')
    args=[media_tool('ffmpeg'),'-nostdin','-hide_banner','-loglevel','error','-y','-ss',str(start),'-i',str(source),'-t',str(end-start),'-filter_complex','[0:v]split=2[bg][fg];[bg]scale=360:640:force_original_aspect_ratio=increase,crop=360:640,boxblur=18:2,scale=1080:1920[blur];[fg]scale=1080:1080:force_original_aspect_ratio=decrease[front];[blur][front]overlay=(W-w)/2:(H-h)/2,setsar=1,fps=30,subtitles=subtitles.ass[out]','-map','[out]','-map','0:a:0?','-filter_complex_threads','1','-c:v','libx264','-preset','fast','-crf','23','-threads','2','-c:a','aac','-b:a','128k','-pix_fmt','yuv420p','-movflags','+faststart',str(output)]
    result=subprocess.run(args,cwd=directory,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=300,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    if result.returncode or not output.is_file():raise RenderError('Local rendering failed.')
    check=subprocess.run([media_tool('ffprobe'),'-v','error','-show_streams','-show_format','-of','json',str(output)],capture_output=True,text=True,timeout=15,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    try:
        data=json.loads(check.stdout);video=next(s for s in data['streams'] if s['codec_type']=='video');duration=float(data['format']['duration'])
        if (video['width'],video['height'],video['codec_name'])!=(1080,1920,'h264') or not 14.5<=duration<=60.5 or not any(s.get('codec_name')=='aac' for s in data['streams']):raise ValueError()
    except (ValueError,KeyError,TypeError,StopIteration):raise RenderError('Rendered clip failed media verification.','render_verify_failed') from None
    final=directory/final_name;output.replace(final);output=final
    digest=hashlib.sha256()
    with output.open('rb') as handle:
        for chunk in iter(lambda:handle.read(1024*1024),b''):digest.update(chunk)
    return {'path':output,'sha256':digest.hexdigest(),'sizeBytes':output.stat().st_size,'duration':duration,'width':1080,'height':1920,'framing':'blurred_fit'}
