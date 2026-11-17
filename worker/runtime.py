from .version import VERSION
from .platforms.identity import current_target
"""Concurrent live monitor loop with bounded queues and explicit cancellation."""
import threading,time,secrets,logging
import httpx
from copy import deepcopy
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from .scout_scheduler import select_sources
from .capture import capture,CaptureError
from .discovery import discover
from .processor import ProcessingQueueFull
from .live_triggers import trigger_settings_ready

class MonitorRuntime:
    def __init__(self,client,root,on_window,capture_function=capture,hardware_slots=2):
        self.client=client;self.root=Path(root).resolve();self.root.mkdir(parents=True,exist_ok=True)
        self.on_window=on_window;self.capture=capture_function;self.hardware_slots=max(1,min(40,hardware_slots))
        self.stop=threading.Event();self.active={};self.rotation=0;self.last_discovery=0;self.sources=[];self.discovery_config=None;self.last_configuration=None
        self.pool=ThreadPoolExecutor(max_workers=40);self.clip_pool=ThreadPoolExecutor(max_workers=2);self.speech_pool=ThreadPoolExecutor(max_workers=1);self.speech_gate=threading.BoundedSemaphore(1);self.clip_gate=threading.BoundedSemaphore(4);self.clip_records={};self.states={};self.sessions={};self.latest={};self.manual_seen={};self.retries={};self.state_lock=threading.Lock()
    def metrics(self):
        import psutil,shutil
        return {'cpuPercent':psutil.cpu_percent(),'memoryPercent':psutil.virtual_memory().percent,'freeDiskBytes':shutil.disk_usage(self.root).free,'activeScouts':len(self.active),'queuedWindows':0}
    def _capture(self,source,event,controls):
        job=None
        try:
            job=self.client.request('POST','/api/worker/jobs/open',{'platform':source['platform'],'login':source['login']})['job']
            self.client.report(job,{'stage':'capturing','metrics':self.metrics()})
            heartbeat_stop=threading.Event()
            def renew():
                while not heartbeat_stop.wait(20):
                    try:self.client.report(job,{'stage':'capturing','metrics':self.metrics()})
                    except Exception:event.set();break
            thread=threading.Thread(target=renew,daemon=True);thread.start()
            try:path=self.capture(source,self.root/job['id'],event,duration=controls.get('captureSeconds',120),gate=controls.get('captureGate','balanced'))
            finally:heartbeat_stop.set();thread.join(timeout=3)
            self.client.report(job,{'stage':'transcribing','metrics':self.metrics()})
            self.on_window(job,path,event)
        except Exception as exc:
            if job:
                try:self.client.report(job,{'stage':'failed','errorCode':'cancelled' if event.is_set() else ('queue_full' if isinstance(exc,ProcessingQueueFull) else 'capture_unavailable')})
                except Exception:pass
    def _set_state(self,identity,**values):
        with self.state_lock:self.states.setdefault(identity,{}).update(values)
    def _watch(self,source,event):
        from .rolling_buffer import RollingBuffer,audio_level,extract
        from .live_triggers import CueDetector
        from .interaction import InteractionWindow
        interaction=InteractionWindow()
        from .chat_relay_client import RelayChatWatcher
        identity=(source['platform'],source['login']);job=None;chat=None;chat_thread=None;cue_lock=threading.Lock()
        detector=CueDetector(self.latest['triggers']);self._set_state(identity,state='connecting',started=time.time(),chatStatus='connecting',speechStatus='waiting',cueStatus='warming_up',interaction=interaction.snapshot())
        directory=self.root/'buffers'/(source['platform']+'-'+source['login'])
        def cue(kind,position=None):
            if kind:interaction.cue(kind,time.time())
            if not cue_lock.acquire(blocking=False):return
            try:return accept_cue(kind,position)
            finally:cue_lock.release()
        def accept_cue(kind,position=None):
            nonlocal job
            if not kind or event.is_set():return
            settings=self.latest;timing=settings['triggers']
            if not trigger_settings_ready(timing):return
            if not settings.get('queueAvailable',True):self._set_state(identity,cueStatus='waiting_for_processing');return
            if job or buffer.pending or not buffer.parts or buffer.media_time-timing['beforeSeconds']<buffer.parts[0][1]:return
            if not self.clip_gate.acquire(blocking=False):self._set_state(identity,cueStatus='waiting_for_processing');return
            try:
                job=self.client.request('POST','/api/worker/jobs/open',{'platform':identity[0],'login':identity[1]})['job']
                job['directory']=str(self.root/job['id']/'buffer-parts')
                if not buffer.trigger(timing['beforeSeconds'],timing['afterSeconds'],job,position):
                    self.client.report(job,{'stage':'failed','errorCode':'cancelled'});job=None;self.clip_gate.release();return
                self.client.report(job,{'stage':'capturing','metrics':self.metrics()});
                with self.state_lock:self.clip_records[job['id']]=job
                job['captureCue']=kind
                interaction.cue('capture',time.time())
                self._set_state(identity,cueStatus='saving_clip',trigger=kind)
            except Exception:
                with buffer.lock:buffer.pending=None
                if job:
                    try:self.client.report(job,{'stage':'failed','errorCode':'capture_unavailable'})
                    except Exception:pass
                job=None;self.clip_gate.release();self._set_state(identity,cueStatus='waiting_for_processing')
        def speech(path,position):
            try:
                processor=getattr(self.on_window,'__self__',None)
                text=processor.cue_transcribe(path) if processor and hasattr(processor,'cue_transcribe') else None
                self._set_state(identity,speechStatus='active' if text is not None else 'waiting')
                if text:cue(detector.speech(text,time.monotonic()),position)
            except Exception:self._set_state(identity,speechStatus='unavailable')
            finally:self.speech_gate.release()
        def segment(path):
            detector.settings=dict(self.latest['triggers'])
            if detector.settings['audioEnabled']:
                try:
                    level=audio_level(path)
                    if level is not None:
                        interaction.audio(level,time.time());cue(detector.audio(level,time.monotonic()))
                except Exception:pass
            if detector.settings['speechEnabled']:
                if self.speech_gate.acquire(blocking=False):self.speech_pool.submit(speech,path,buffer.media_time)
                else:self._set_state(identity,speechStatus='waiting')
            else:self._set_state(identity,speechStatus='disabled')
            if buffer.media_time>=detector.settings['beforeSeconds'] and not buffer.pending:self._set_state(identity,cueStatus='watching_for_cues')
        def ready(parts,start,end,record):
            nonlocal job
            with cue_lock:job=None
            def finish():
                try:
                    path=extract(parts,start,end,self.root/record['id'],event)
                    self.client.report(record,{'stage':'transcribing','metrics':self.metrics()});self.on_window(record,path,event)
                except Exception:
                    try:self.client.report(record,{'stage':'failed','errorCode':'cancelled' if event.is_set() else 'capture_unavailable'})
                    except Exception:pass
                finally:
                    for part,a,b in parts:part.unlink(missing_ok=True)
                    with self.state_lock:self.clip_records.pop(record['id'],None)
                    self.clip_gate.release()
            self.clip_pool.submit(finish);self._set_state(identity,cueStatus='watching_for_cues')
        buffer=RollingBuffer(source,directory,event,segment,ready,lambda status:self._set_state(identity,state=status));self.sessions[identity]=cue
        def chat_message(text,stamp):
            interaction.chat(time.time()-max(0,time.monotonic()-stamp))
            age=max(0,time.monotonic()-stamp);position=buffer.media_time+min(8,max(0,time.monotonic()-buffer.completed_at))-age
            cue(detector.chat(text,stamp),position)
        chat=RelayChatWatcher(self.client,source,chat_message,event)
        chat_thread=threading.Thread(target=chat.run,daemon=True)
        enabled_chat=self.latest['triggers']['chatEnabled'] or self.latest['triggers']['chatSpikeEnabled']
        if enabled_chat:chat_thread.start()
        else:chat.status='disabled'
        renew_stop=threading.Event()
        def renew():
            nonlocal chat,chat_thread,enabled_chat
            while not renew_stop.wait(5):
                enabled=self.latest['triggers']['chatEnabled'] or self.latest['triggers']['chatSpikeEnabled']
                if enabled!=enabled_chat:
                    chat.close()
                    if chat_thread.is_alive():chat_thread.join(timeout=1)
                    chat=RelayChatWatcher(self.client,source,chat_message,event);chat_thread=threading.Thread(target=chat.run,daemon=True)
                    if enabled:chat_thread.start()
                    else:chat.status='disabled'
                    enabled_chat=enabled
                interaction.observe(time.time(),chat_connected=chat.status=='connected')
                self._set_state(identity,chatStatus=chat.status,interaction=interaction.snapshot())
                with self.state_lock:records=[r for r in self.clip_records.values() if r['source']['platform']==identity[0] and r['source']['login']==identity[1]]
                for record in records:
                    try:self.client.report(record,{'stage':'capturing','metrics':self.metrics()})
                    except Exception:pass
        renew_thread=threading.Thread(target=renew,daemon=True);renew_thread.start()
        try:buffer.run()
        except Exception:
            self.retries[identity]=time.monotonic()+15;self._set_state(identity,state='reconnecting')
        finally:
            renew_stop.set();chat.close();
            if chat_thread.is_alive():chat_thread.join(timeout=2)
            renew_thread.join(timeout=2);self.sessions.pop(identity,None)
            if job:
                try:self.client.report(job,{'stage':'failed','errorCode':'cancelled' if event.is_set() else 'capture_unavailable'})
                except Exception:pass
                with self.state_lock:self.clip_records.pop(job['id'],None)
                self.clip_gate.release()
    def tick(self):
        try:settings=self.client.configuration()
        except httpx.TransportError:
            logging.getLogger(__name__).warning('Worker configuration connection unavailable; retrying.')
            # Keep local buffers briefly, but do not open new clips without current authorization.
            self.latest={**self.latest,'queueAvailable':False}
            if self.last_configuration is None or time.monotonic()-self.last_configuration>=60:
                for future,event in self.active.values():event.set()
            return
        self.last_configuration=time.monotonic();self.latest=settings;config=settings['effective'];self.hardware_slots=max(1,config['slots']);capacity=min(config['slots'],self.hardware_slots)
        triggers_unavailable=self.capture is capture and not trigger_settings_ready(settings.get('triggers'))
        if triggers_unavailable:
            self.latest={**settings,'queueAvailable':False};config={**config,'running':False}
        legacy_feedback_required=settings.get('betaAccepted') is False and settings.get('customerAnalysisEnabled') is not True
        if settings.get('analysisEnabled') is False or legacy_feedback_required:config={**config,'running':False}
        if config['running'] and ((self.discovery_config is not None and config!=self.discovery_config) or time.monotonic()-self.last_discovery>=30):
            try:discovered=discover(self.client)
            except (httpx.HTTPError,RuntimeError,ConnectionError):
                logging.getLogger(__name__).warning('Stream discovery unavailable; retaining active source metadata.')
                discovered={'sources':[],'errors':[{'platform':platform,'code':'discovery_unavailable'} for platform in ('twitch','kick')]}
            unavailable={error['platform'] for error in discovered.get('errors',[]) if error.get('code')=='discovery_unavailable'}
            # A provider failure is not an offline confirmation; let healthy active ingests continue.
            retained_sources=[source for source in self.sources if source['platform'] in unavailable and (source['platform'],source['login']) in self.active]
            self.sources=discovered['sources']+retained_sources;self.last_discovery=time.monotonic();self.discovery_config=deepcopy(config)
        completed=0
        for identity,(future,event) in list(self.active.items()):
            if future.done():del self.active[identity];completed+=1
        self.rotation+=completed if 'triggers' not in settings else 0
        blocked=set() if 'triggers' in settings else {(v['platform'],v['login']) for v in settings.get('blockedSources',[])}
        eligible=[v for v in self.sources if (v['platform'],v['login']) not in blocked or (v['platform'],v['login']) in self.active]
        # Explicit selections always outrank retained automatic scouts.
        retained=[identity for identity,(future,event) in self.active.items() if not event.is_set()]
        selected=select_sources(config,eligible,capacity,self.rotation,retained=retained)
        wanted={(s['platform'],s['login']) for s in selected}
        for identity,(future,event) in list(self.active.items()):
            if identity not in wanted:event.set()
            if future.done():del self.active[identity]
        for source in selected:
            identity=(source['platform'],source['login'])
            if (settings.get('queueAvailable',True) or (self.capture is capture and 'triggers' in settings)) and identity not in self.active and len(self.active)<capacity and self.retries.get(identity,0)<=time.monotonic():
                event=threading.Event();future=self.pool.submit(self._watch,source,event) if self.capture is capture and 'triggers' in settings else self.pool.submit(self._capture,source,event,dict(settings.get('controls',{})));self.active[identity]=(future,event)
        with self.state_lock:records=list(self.clip_records.values())
        for record in records:
            try:self.client.report(record,{'stage':'capturing','metrics':self.metrics()})
            except Exception:pass
        for request in settings.get('manualTriggers',[]):
            identity=(request['platform'],request['login'])
            if request['nonce']!=self.manual_seen.get(identity) and identity in self.sessions:
                self.manual_seen[identity]=request['nonce'];self.sessions[identity]('manual')
        try:
            if hasattr(self.client,'companion_heartbeat'):
                requested=settings.get('configuration',settings['effective'])['running']
                error='coverage_unavailable' if requested and settings['effective']['slots']<=0 else 'trigger_settings_unavailable' if triggers_unavailable and requested else 'analysis_paused' if settings.get('analysisEnabled') is False and requested else 'beta_required' if legacy_feedback_required and requested else None
                monitored={identity for identity,(future,event) in self.active.items() if not future.done() and not event.is_set()}
                self.client.companion_heartbeat({'version':VERSION,'platformTarget':current_target(),'ready':True,'monitoring':bool(config['running'] or any(not future.done() for future,event in self.active.values())),'acknowledgedRevision':settings.get('revision',''),'hardwareSlots':self.hardware_slots,'activeScouts':len(monitored),'errorCode':error,**({'monitoredSources':[{'platform':identity[0],'login':identity[1],**self.states.get(identity,{'state':'connecting','started':time.time(),'chatStatus':'connecting','speechStatus':'waiting','cueStatus':'warming_up'})} for identity in monitored]} if 'triggers' in settings else {})})
            else:self.client.heartbeat()
        except httpx.TransportError:
            logging.getLogger(__name__).warning('Worker heartbeat connection unavailable; retrying.')
    def run(self):
        try:
            while not self.stop.is_set():self.tick();self.stop.wait(5)
        finally:self.close()
    def close(self):
        self.stop.set()
        for future,event in self.active.values():event.set()
        self.pool.shutdown(wait=True,cancel_futures=True);self.speech_pool.shutdown(wait=True,cancel_futures=True);self.clip_pool.shutdown(wait=True,cancel_futures=False)
