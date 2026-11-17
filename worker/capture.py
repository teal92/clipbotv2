"""Bounded cancellable local live capture. Provider/CDN URLs never enter logs."""
from .tools import media_tool
import json,os,re,shutil,subprocess,sys,time
import certifi
from pathlib import Path
from urllib.parse import urlsplit

class CaptureError(RuntimeError):pass

def capture_tls_options(platform=None):
    # Native OpenSSL builds must not depend on a build machine's CA paths.
    # Windows Schannel verifies against its operating-system certificate store.
    return ['-tls_verify','1']+([] if (platform or sys.platform)=='win32' else ['-ca_file',certifi.where()])

def stream_url(source):
    if not isinstance(source,dict) or source.get('platform') not in ('twitch','kick') or not isinstance(source.get('login'),str) or not re.fullmatch(r'[a-zA-Z0-9_-]{1,35}' if source.get('platform')=='kick' else r'[a-zA-Z0-9_]{1,35}',source['login']):raise CaptureError('Invalid live source.')
    root='https://www.twitch.tv/' if source['platform']=='twitch' else 'https://kick.com/'
    return root+source['login'].lower()

def validate_media_url(url,platform):
    p=urlsplit(url);domains={'twitch':('ttvnw.net','twitchcdn.net'),'kick':('live-video.net','kick.com','kickcdn.com')}.get(platform,())
    if p.scheme!='https' or p.username or p.password or p.port not in (None,443) or p.fragment or not any(p.hostname==d or (p.hostname or '').endswith('.'+d) for d in domains):raise CaptureError('The provider returned an unsupported media endpoint.')
    return url

def resolve(source):
    # yt-dlp receives a fixed provider URL and ignores local/global config files.
    command=[media_tool('yt-dlp')] if getattr(sys,'frozen',False) else [sys.executable,'-m','yt_dlp']
    result=subprocess.run(command+['--ignore-config','--no-plugin-dirs','--no-remote-components','--no-js-runtimes','--no-playlist','--socket-timeout','10','--retries','0','-f','best[height<=720]/best','-g',stream_url(source)],stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,text=True,timeout=30,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    lines=result.stdout.strip().splitlines()
    if result.returncode or len(lines)!=1:raise CaptureError('Live ingest is unavailable for this source.')
    return validate_media_url(lines[0],source['platform'])

def probe(path):
    result=subprocess.run([media_tool('ffprobe'),'-v','error','-show_entries','format=duration:stream=codec_type','-of','json',str(path)],capture_output=True,text=True,timeout=15,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    if result.returncode:raise CaptureError('Captured media could not be verified.')
    try:
        data=json.loads(result.stdout);duration=float(data['format']['duration'])
        if not 0<duration<=305 or not any(s.get('codec_type')=='video' for s in data['streams']):raise ValueError()
    except (KeyError,ValueError,TypeError):raise CaptureError('Captured media could not be verified.') from None
    return duration

def capture(source,job_directory,stop_event,duration=120,resolver=None,popen=None,disk_free=None,gate='balanced'):
    stream_url(source)
    if type(duration) is not int or not 15<=duration<=300:raise CaptureError('Choose a bounded capture window.')
    directory=Path(job_directory).resolve();directory.mkdir(parents=True,exist_ok=True)
    disk_free=disk_free or (lambda p:shutil.disk_usage(p).free)
    def check():
        if stop_event.is_set():raise CaptureError('Capture cancelled.')
        if disk_free(directory)<2*1024**3:raise CaptureError('Capture paused: insufficient disk headroom.')
    check();media=validate_media_url((resolver or resolve)(source),source['platform'])
    output=directory/'capture.mkv'
    # Deny file/http protocols in remote manifests and never interpolate a shell command.
    args=[media_tool('ffmpeg'),'-nostdin','-hide_banner','-loglevel','error','-y','-protocol_whitelist','https,tls,tcp,crypto','-rw_timeout','15000000',*capture_tls_options(),'-i',media,'-t',str(duration),'-map','0:v:0','-map','0:a:0?','-c','copy',str(output)]
    process=(popen or subprocess.Popen)(args,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,shell=False,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    deadline=time.monotonic()+duration+45
    try:
        while process.poll() is None:
            check()
            if time.monotonic()>deadline:raise CaptureError('Live capture timed out.')
            stop_event.wait(.25)
        if process.returncode:raise CaptureError('Live capture stopped before completing.')
        actual=probe(output)
        if not capture_quality_allowed(actual,duration,gate):raise CaptureError('Captured window did not meet the selected quality gate.')
        return output
    finally:
        if process.poll() is None:process.kill();process.wait(timeout=10)

def capture_quality_allowed(actual,requested,gate):
    if gate not in ('strict','balanced','review') or not 15<=actual<=305:return False
    ratio=actual/requested
    return gate=='review' or ratio>=(.9 if gate=='strict' else .5)
