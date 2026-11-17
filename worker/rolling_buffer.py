"""Continuous local stream ingest with bounded segments and triggered clip extraction."""
from .tools import media_tool
import array,math,os,re,shutil,subprocess,threading,time
from pathlib import Path
from .capture import CaptureError,resolve,validate_media_url,stream_url,probe,capture_tls_options

FLAGS=getattr(subprocess,'CREATE_NO_WINDOW',0)
MAX_BUFFER_BYTES=128*1024**2

def selected_parts(parts,start,end):
    return [p for p in parts if p[2]>start and p[1]<end]

def audio_level(path):
    r=subprocess.run([media_tool('ffmpeg'),'-nostdin','-v','error','-i',str(path),'-vn','-ac','1','-ar','8000','-t','12','-f','s16le','pipe:1'],stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,timeout=15,creationflags=FLAGS)
    if r.returncode or not r.stdout:return None
    pcm=array.array('h');pcm.frombytes(r.stdout[:192000]);energy=sum(n*n for n in pcm)/max(1,len(pcm))
    return 20*math.log10(max(1,math.sqrt(energy))/32768)

def extract(parts,start,end,directory,stop):
    if stop.is_set():raise CaptureError('Clip extraction cancelled.')
    chosen=selected_parts(parts,start,end)
    if not chosen or start<chosen[0][1]-.5 or end>chosen[-1][2]+.5:raise CaptureError('The stream buffer did not cover the requested clip.')
    directory=Path(directory).resolve();directory.mkdir(parents=True,exist_ok=True)
    copies=[];process=None
    try:
        for i,(path,a,b) in enumerate(chosen):
            target=directory/f'part-{i:03}.mkv'
            try:os.link(path,target)
            except OSError:shutil.copyfile(path,target)
            copies.append(target)
        listing=directory/'parts.txt';listing.write_text(''.join(f"file '{p.name}'\n" for p in copies),encoding='utf-8')
        output=directory/'capture.mkv'
        args=[media_tool('ffmpeg'),'-nostdin','-hide_banner','-loglevel','error','-y','-f','concat','-safe','1','-i',str(listing),'-ss',str(max(0,start-chosen[0][1])),'-t',str(end-start),'-map','0:v:0','-map','0:a:0?','-vf','scale=960:-2','-c:v','libx264','-preset','ultrafast','-crf','26','-threads','2','-c:a','aac',str(output)]
        process=subprocess.Popen(args,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,creationflags=FLAGS,shell=False)
        deadline=time.monotonic()+180
        while process.poll() is None:
            if stop.wait(.2) or time.monotonic()>deadline:raise CaptureError('Clip extraction cancelled or timed out.')
        if process.returncode or abs(probe(output)-(end-start))>.8:raise CaptureError('The selected clip could not be verified.')
        return output
    finally:
        if process and process.poll() is None:process.kill();process.wait(timeout=10)
        for p in copies:p.unlink(missing_ok=True)
        (directory/'parts.txt').unlink(missing_ok=True)

class RollingBuffer:
    def __init__(self,source,directory,stop,on_segment,on_ready,status):
        stream_url(source);self.source=source;self.directory=Path(directory).resolve();self.stop=stop
        self.on_segment=on_segment;self.on_ready=on_ready;self.status=status;self.parts=[];self.media_time=0;self.completed_at=time.monotonic();self.pending=None;self.lock=threading.Lock()
    def trigger(self,before,after,job,position=None):
        with self.lock:
            position=self.media_time+min(8,max(0,time.monotonic()-self.completed_at)) if position is None else position
            if self.pending or not self.parts or position-before<self.parts[0][1]:return False
            self.pending=(position-before,position+after,job);return True
    def run(self):
        self.directory.mkdir(parents=True,exist_ok=True)
        # This directory is a fixed child owned by one source; only numbered segments are removed.
        for p in self.directory.glob('segment-*.mkv'):
            if re.fullmatch(r'segment-[0-9]{8}\.mkv',p.name) and p.resolve().parent==self.directory:p.unlink()
        if self.stop.is_set():return
        if shutil.disk_usage(self.directory).free<2*1024**3:raise CaptureError('Insufficient disk headroom.')
        media=validate_media_url(resolve(self.source),self.source['platform'])
        args=[media_tool('ffmpeg'),'-nostdin','-hide_banner','-loglevel','error','-y','-protocol_whitelist','https,tls,tcp,crypto','-rw_timeout','15000000',*capture_tls_options(),'-i',media,'-map','0:v:0','-map','0:a:0?','-c','copy','-f','segment','-segment_time','5','-reset_timestamps','1',str(self.directory/'segment-%08d.mkv')]
        process=subprocess.Popen(args,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,creationflags=FLAGS,shell=False)
        seen=set();last_progress=time.monotonic()
        try:
            while not self.stop.wait(.5):
                if process.poll() is not None:raise CaptureError('Live stream ingest disconnected.')
                files=sorted(self.directory.glob('segment-*.mkv'))
                if shutil.disk_usage(self.directory).free<2*1024**3:raise CaptureError('Insufficient disk headroom.')
                if sum(p.stat().st_size for p in files)>MAX_BUFFER_BYTES:raise CaptureError('Stream buffer storage limit reached.')
                for path in files[:-1]:
                    if path.name in seen:continue
                    duration=probe(path)
                    with self.lock:
                        part=(path,self.media_time,self.media_time+duration);self.parts.append(part);self.media_time+=duration;self.completed_at=time.monotonic();seen.add(path.name)
                    last_progress=time.monotonic();self.status('monitoring');self.on_segment(path)
                ready_payload=None
                with self.lock:
                    if self.pending and self.media_time>=self.pending[1]:
                        start,end,job=self.pending;chosen=selected_parts(self.parts,start,end)
                        # Pin segments before buffer cleanup while extraction happens separately.
                        pins=Path(job['directory']);pins.mkdir(parents=True,exist_ok=True);pinned=[]
                        for i,(path,a,b) in enumerate(chosen):
                            target=pins/f'segment-{i:08d}.mkv'
                            try:os.link(path,target)
                            except OSError:shutil.copyfile(path,target)
                            pinned.append((target,a,b))
                        self.pending=None;ready_payload=(pinned,start,end,job)
                    retain=self.pending[0]-10 if self.pending else self.media_time-80
                    while self.parts and self.parts[0][2]<retain:
                        old=self.parts.pop(0)[0];old.unlink(missing_ok=True);seen.discard(old.name)
                if ready_payload:self.on_ready(*ready_payload)
                if time.monotonic()-last_progress>45:raise CaptureError('Live stream stopped providing footage.')
        finally:
            if process.poll() is None:process.kill();process.wait(timeout=10)
            for p in self.directory.glob('segment-*.mkv'):
                if re.fullmatch(r'segment-[0-9]{8}\.mkv',p.name) and p.resolve().parent==self.directory:p.unlink(missing_ok=True)
