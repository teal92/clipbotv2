"""Bounded local transcript/render queue and consented upload handoff."""
import hashlib,json,re,secrets,threading,time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from .capture import probe
from .transcribe import load_model,transcribe
from .render import render
from .upload import upload
from .observability import trace

class ProcessingQueueFull(RuntimeError):pass

class ClipProcessor:
    def __init__(self,client,root,model_directory,previews):
        self.client=client;self.root=Path(root).resolve();self.model=load_model(model_directory);self.previews=previews
        self.pool=ThreadPoolExecutor(max_workers=1);self.preview_pool=ThreadPoolExecutor(max_workers=1);self.lock=threading.Lock();self.pending=threading.BoundedSemaphore(40)
        self.model_lock=threading.Lock()
        self.entries={};self.stop=threading.Event();self.last_error='';self.upload_busy=set()
        self.personal_memory=None;self.memory_binding=None;self.davey_state={}
    def _bind_memory(self,remote):
        from .personal_memory import PersonalMemory
        uid=remote.get('userId') if isinstance(remote,dict) else None
        origin=getattr(self.client,'origin',None);token=getattr(self.client,'token',None)
        if not isinstance(uid,str) or not re.fullmatch(r'[a-f0-9]{32}',uid) or not isinstance(origin,str) or not isinstance(token,str):
            self.personal_memory=None;self.memory_binding=None;self.davey_state={};return
        binding=(uid,origin,hashlib.sha256(token.encode()).hexdigest())
        if binding!=self.memory_binding:
            self.personal_memory=PersonalMemory(self.root.parent/'personal-memory',origin,uid);self.memory_binding=binding
        self.davey_state=remote.get('davey',{}) if isinstance(remote.get('davey'),dict) else {}
        self.personal_memory.apply_reset(self.davey_state.get('memoryResetAt',0))
    def _trace(self,entry,event,source='processing',level='info',**fields):
        job=entry['job'];trace(event,job,**fields)
        if hasattr(self.client,'diagnostic') and job.get('lease'):
            try:self.client.diagnostic({'jobId':job['id'],'lease':job['lease'],'event':event,'source':source,'level':level,**{k:v for k,v in fields.items() if k!='exceptionType'}})
            except Exception:pass
    def submit(self,job,path,event):
        if not self.pending.acquire(blocking=False):raise ProcessingQueueFull('Local processing queue is full.')
        with self.lock:self.entries[job['id']]={'job':job,'path':Path(path),'event':threading.Event(),'phase':'transcribing'}
        (Path(path).parent/'job.json').write_text(json.dumps({'id':job['id'],'source':job['source']}),encoding='utf-8')
        self.pool.submit(self._analyze,job['id'])
    def _analyze(self,job_id):
        entry=self.entries[job_id];job=entry['job'];error_code='transcription_unavailable';started=time.monotonic()
        self._trace(entry,'transcription_started',source='transcription',stage='transcribing')
        try:
            if self.stop.is_set() or entry['event'].is_set():raise RuntimeError('Job cancelled.')
            duration=probe(entry['path'])
            with self.model_lock:transcript=entry.get('transcript') or transcribe(entry['path'],self.model,duration=duration)
            self._trace(entry,'transcription_completed',source='transcription',stage='transcribing',elapsedMs=int((time.monotonic()-started)*1000))
            if not transcript:
                entry['phase']='failed';self.client.report(job,{'stage':'failed','errorCode':'no_speech'});return
            error_code='processing_failed'
            (entry['path'].parent/'transcript.json').write_text(json.dumps(transcript),encoding='utf-8')
            if self.stop.is_set() or entry['event'].is_set():return
            personal={}
            if self.personal_memory and self.davey_state.get('personalContext') is True:
                binding=self.memory_binding;self._bind_memory(self.client.request('GET','/api/worker/state'))
                if binding!=self.memory_binding:raise RuntimeError('The paired account changed before analysis.')
                revision=self.davey_state.get('revision')
                if self.davey_state.get('personalContext') is True and type(revision) is int:
                    personal={'personalPreferences':self.personal_memory.summary(),'personalPreferencesRevision':revision}
            result=self.client.request('POST','/api/worker/analyze',{'jobId':job['id'],'lease':job['lease'],'duration':duration,'transcript':transcript,**personal,**({'captureCue':job['captureCue']} if job.get('captureCue') is not None else {})})
            if not result['candidate']:entry['phase']='failed';return
            entry.update(transcript=transcript,candidate=result['candidate'],phase='review')
            (entry['path'].parent/'transcript.json').write_text(json.dumps(transcript),encoding='utf-8')
            (entry['path'].parent/'candidate.json').write_text(json.dumps(result['candidate']),encoding='utf-8')
        except Exception as exc:
            if isinstance(exc,TypeError) and 'metadata_errors' in str(exc):error_code='dependency_mismatch'
            failure=getattr(exc,'code',error_code)
            status=getattr(exc,'http_status',None)
            self._trace(entry,'worker_request_failed',level='error',code=failure,exceptionType=type(exc).__name__,**({'details':{'httpStatus':status}} if type(status) is int and 400<=status<=599 else {}))
            entry['phase']='failed';self.last_error='Analysis stopped. Check Streamers preferences, feedback privacy and your plan allowance in ClipBot.'
            try:self.client.report(job,{'stage':'failed','errorCode':failure})
            except Exception:pass
        finally:self.pending.release()
    def cue_transcribe(self,path):
        # Reuse the installed model; clip transcription has priority over cue sampling.
        if self.stop.is_set() or not self.model_lock.acquire(blocking=False):return None
        try:return ' '.join(v['text'] for v in transcribe(path,self.model))
        finally:self.model_lock.release()
    def _prepare_artifact(self,entry):
        with entry.setdefault('render_lock',threading.Lock()):
            if self.stop.is_set() or entry['event'].is_set():raise RuntimeError('Job cancelled.')
            artifact=entry.get('artifact')
            if not artifact or artifact.get('framing')!='blurred_fit':
                artifact=render(entry['candidate'],entry['path'],entry['transcript'],entry['path'].parent)
                entry['artifact']=artifact
            return artifact
    def _preview(self,job_id):
        entry=self.entries[job_id];job=entry['job'];started=time.monotonic()
        try:
            if self.stop.is_set() or entry['event'].is_set():return
            self._trace(entry,'render_started',source='rendering',stage='review')
            artifact=self._prepare_artifact(entry)
            path=artifact['path']
            self._trace(entry,'render_completed',source='rendering',stage='review',elapsedMs=int((time.monotonic()-started)*1000))
            if self.stop.is_set() or entry['event'].is_set():return
            capability=secrets.token_hex(32)
            self.client.request('POST','/api/worker/render-ready',{'jobId':job['id'],'lease':job['lease'],'artifact':{k:v for k,v in artifact.items() if k!='path'},'previewToken':capability})
            with self.lock:
                if self.stop.is_set() or entry['event'].is_set():return
                self.previews[capability]=path;entry['review_preview']=capability;entry['artifact']=artifact
            self._trace(entry,'preview_ready',source='rendering',stage='review')
        except Exception as exc:
            self._trace(entry,'preview_failed',source='rendering',level='error',code=getattr(exc,'code','render_timeout' if isinstance(exc,__import__('subprocess').TimeoutExpired) else 'render_tool_missing' if isinstance(exc,FileNotFoundError) else 'processing_failed'),exceptionType=type(exc).__name__)
            self.last_error='Captioned mobile preview could not be prepared. Check Logs in ClipBot.'
            entry['preview_retry_after']=time.monotonic()+60;entry['preview_attempts']=entry.get('preview_attempts',0)+1
    def _render(self,job_id):
        entry=self.entries[job_id];job=entry['job'];started=time.monotonic()
        try:
            if self.stop.is_set() or entry['event'].is_set():return
            artifact=self._prepare_artifact(entry)
            if self.stop.is_set() or entry['event'].is_set():return
            capability=secrets.token_hex(32)
            metadata={k:v for k,v in artifact.items() if k!='path'}
            self.client.request('POST','/api/worker/render-ready',{'jobId':job['id'],'lease':job['lease'],'artifact':metadata,'previewToken':capability})
            with self.lock:
                if self.stop.is_set() or entry['event'].is_set():return
                self.previews[capability]=artifact['path']
                entry.update(phase='ready',artifact=artifact)
        except Exception as exc:
            self._trace(entry,'render_failed',source='rendering',level='error',code=getattr(exc,'code','render_timeout' if isinstance(exc,__import__('subprocess').TimeoutExpired) else 'render_tool_missing' if isinstance(exc,FileNotFoundError) else 'processing_failed'),exceptionType=type(exc).__name__)
            entry['phase']='failed';self.last_error='Rendering stopped. Check Processing in ClipBot.'
            try:self.client.report(job,{'stage':'failed','errorCode':'processing_failed'})
            except Exception:pass
    def start_edit(self,job_id,preview_token,values):
        with self.lock:
            entry=self.entries.get(job_id)
            if not entry or entry.get('phase')!='review' or entry.get('review_preview')!=preview_token or entry.get('edit_busy') or not entry.get('transcript'):
                raise ValueError('Reopen an undecided clip with the updated companion before editing.')
            entry['edit_busy']=True;entry['edit_status']={'status':'saving'}
        try:
            result=self.client.request('POST','/api/worker/clip-edits/begin',{'jobId':job_id,'lease':entry['job']['lease'],'previewToken':preview_token,**values})
            entry['phase']='editing';entry['edit_id']=result['editId']
            self.preview_pool.submit(self._edit,entry,result['candidate'],preview_token)
        except Exception:
            entry['edit_busy']=False;entry['edit_status']={'status':'failed'};raise
        return {'ok':True,'status':'saving'}
    def _edit(self,entry,candidate,previous_token):
        job=entry['job'];artifact=None;capability=secrets.token_hex(32)
        try:
            with entry.setdefault('render_lock',threading.Lock()):
                if self.stop.is_set() or entry['event'].is_set():raise RuntimeError('Edit stopped.')
                artifact=render(candidate,entry['path'],entry['transcript'],entry['path'].parent,final_name='clip-edit-'+entry['edit_id']+'.mp4')
                if self.stop.is_set() or entry['event'].is_set():raise RuntimeError('Edit stopped.')
                payload={'jobId':job['id'],'editId':entry['edit_id'],'artifact':{k:v for k,v in artifact.items() if k!='path'},'previewToken':capability}
                try:self.client.request('POST','/api/worker/clip-edits/complete',payload)
                except Exception:self.client.request('POST','/api/worker/clip-edits/complete',payload)
                final=artifact['path']
                (entry['path'].parent/'artifact-recovery.json').write_text(json.dumps({'sha256':artifact['sha256'],'file':final.name}),encoding='utf-8')
                (entry['path'].parent/'candidate.json').write_text(json.dumps(candidate),encoding='utf-8')
                with self.lock:
                    self.previews[capability]=final
                    entry.update(candidate=candidate,artifact=artifact,phase='review',review_preview=capability,preview_requested=True,edit_status={'status':'complete','previewToken':capability})
        except Exception:
            try:self.client.request('POST','/api/worker/clip-edits/abort',{'jobId':job['id'],'editId':entry['edit_id']})
            except Exception:pass
            entry['phase']='review';entry['edit_status']={'status':'failed'}
        finally:entry['edit_busy']=False
    def _upload(self,attempt,entry):
        self._trace(entry,'upload_started',source='publishing',stage='publishing')
        try:
            if self.stop.is_set() or entry['event'].is_set():return
            grant=self.client.request('POST','/api/worker/upload-grant',{'attemptId':attempt['id']})
            if self.stop.is_set() or entry['event'].is_set():return
            upload(entry['artifact']['path'],grant)
            self.client.request('POST','/api/worker/uploaded',{'attemptId':attempt['id']})
        except Exception as exc:
            self._trace(entry,'upload_failed',source='publishing',level='error',exceptionType=type(exc).__name__)
            self.last_error='Upload outcome needs checking. Use Check provider status in ClipBot; automatic re-upload is disabled.'
    def restore(self,current):
        identity=current['id'];stage=current['stage']
        if stage=='editing' and current.get('leaseExpires',0)<=time.time():
            self.client.request('POST','/api/worker/clip-edits/abort-stale',{'jobId':identity});return
        if self.stop.is_set() or identity in self.entries or not re.fullmatch(r'[a-f0-9]{32}',identity) or stage not in ('transcribing','analyzing','review','rendering','ready','publishing','published'):return
        directory=(self.root/identity).resolve()
        if directory.parent!=self.root:return
        path=directory/'capture.mkv';metadata=current.get('artifact')
        entry={'job':{'id':identity,'source':current['source']},'path':path,'event':threading.Event(),'phase':stage}
        if metadata and stage in ('ready','publishing','published'):
            output=directory/'clip.mp4'
            recovery=directory/'artifact-recovery.json'
            if metadata and recovery.is_file() and recovery.stat().st_size<1024 and recovery.resolve().parent==directory:
                record=json.loads(recovery.read_text(encoding='utf-8'))
                if record.get('sha256')==metadata['sha256'] and re.fullmatch(r'clip-edit-[a-f0-9]{32}\.mp4',record.get('file','')):output=directory/record['file']
            if not output.is_file() or output.resolve().parent!=directory or output.stat().st_size!=metadata['sizeBytes']:return
            digest=hashlib.sha256()
            with output.open('rb') as handle:
                for chunk in iter(lambda:handle.read(1024*1024),b''):digest.update(chunk)
            if digest.hexdigest()!=metadata['sha256'] or not re.fullmatch(r'[a-f0-9]{64}',metadata.get('previewToken','')):return
            entry['artifact']={**metadata,'path':output}
            with self.lock:
                if self.stop.is_set():return
                self.entries[identity]=entry;self.previews[metadata['previewToken']]=output
            return
        if current.get('leaseExpires',0)>time.time() or not path.is_file() or path.resolve().parent!=directory:return
        if current.get('analysisStatus') not in (None,'settled'):self.last_error='A previous paid analysis needs reconciliation. Automatic retries are disabled.';return
        transcript_path=directory/'transcript.json'
        if transcript_path.is_file():
            if transcript_path.stat().st_size>131072 or transcript_path.resolve().parent!=directory:return
            transcript=json.loads(transcript_path.read_text(encoding='utf-8'))
        elif stage=='transcribing' and current.get('analysisStatus') is None:transcript=None
        else:return
        if stage in ('review','rendering') and not current.get('candidate'):return
        resumed=self.client.request('POST','/api/worker/jobs/resume',{'jobId':identity})['job']
        entry.update(job=resumed,transcript=transcript,candidate=current.get('candidate'),phase='review' if stage=='rendering' else resumed['stage'])
        output=directory/'clip.mp4'
        recovery=directory/'artifact-recovery.json'
        if metadata and recovery.is_file() and recovery.stat().st_size<1024 and recovery.resolve().parent==directory:
            record=json.loads(recovery.read_text(encoding='utf-8'))
            if record.get('sha256')==metadata['sha256'] and re.fullmatch(r'clip-edit-[a-f0-9]{32}\.mp4',record.get('file','')):output=directory/record['file']
        if metadata and metadata.get('framing')=='blurred_fit' and output.is_file() and output.resolve().parent==directory and output.stat().st_size==metadata['sizeBytes']:
            with output.open('rb') as stream:digest=hashlib.file_digest(stream,'sha256').hexdigest()
            if digest==metadata['sha256']:entry['artifact']={**metadata,'path':output}
        with self.lock:
            if self.stop.is_set():return
            self.entries[identity]=entry
        if resumed['stage']=='transcribing':
            if self.pending.acquire(blocking=False):self.pool.submit(self._analyze,identity)
            else:self.entries.pop(identity,None)
    def tick(self):
        if self.stop.is_set():return
        state=self.client.request('GET','/api/worker/state');self._bind_memory(state);jobs={j['id']:j for j in state['jobs']}
        if self.davey_state.get('automaticEnabled') is True:
            try:self.client.request('POST','/api/worker/davey-dispatch',{})
            except Exception:self.last_error='Automatic posting paused. Check Davey controls and publishing logs.'
        for current in state['jobs']:
            try:self.restore(current)
            except Exception:self.last_error='A local job could not be restored. Check Processing in ClipBot.'
        with self.lock:entries=list(self.entries.items())
        for identity,entry in entries:
            current=jobs.get(identity)
            if not current:continue
            stage=current['stage']
            if stage in ('failed','cancelled'):
                with self.lock:
                    entry['event'].set();entry['phase']=stage
                    directory=entry['path'].resolve().parent
                    for token,path in list(self.previews.items()):
                        if path.resolve().parent==directory:self.previews.pop(token,None)
                continue
            if stage in ('transcribing','analyzing','review','rendering'):
                try:self.client.report(entry['job'],{'stage':stage})
                except Exception:pass
            if stage=='review' and entry.get('candidate') and (not entry.get('preview_requested') or entry.get('preview_retry_after',float('inf'))<=time.monotonic() and entry.get('preview_attempts',0)<2):
                entry['preview_requested']=True;entry['preview_retry_after']=float('inf');self.preview_pool.submit(self._preview,identity)
            if stage=='rendering' and entry['phase']=='review':
                entry['phase']='rendering';self.pool.submit(self._render,identity)
        for attempt in state['publications']:
            entry=self.entries.get(attempt['clipId'])
            if attempt['status']=='prepared' and entry and entry.get('artifact') and attempt['id'] not in self.upload_busy:
                self.upload_busy.add(attempt['id']);self.pool.submit(self._upload,attempt,entry)
            elif attempt['status'] in ('uploaded','finishing','uploading','unknown'):
                try:self.client.request('POST','/api/worker/publication-status',{'attemptId':attempt['id']})
                except Exception:pass
    def close(self):
        with self.lock:
            self.stop.set()
            for entry in self.entries.values():entry['event'].set()
            self.previews.clear()
        self.pool.shutdown(wait=True,cancel_futures=True);self.preview_pool.shutdown(wait=True,cancel_futures=True)
