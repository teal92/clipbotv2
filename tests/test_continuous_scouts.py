import time
import threading
import pytest
from threading import Event
from worker.runtime import MonitorRuntime
from server.trigger_settings import default_trigger_settings

def test_continuous_monitoring_survives_processing_backpressure(tmp_path,monkeypatch):
 started=[];reports=[]
 class Buffer:
  def __init__(self,source,directory,event,*args):self.source=source;self.event=event;self.parts=[];self.media_time=0;self.pending=None
  def run(self):started.append(self.source['login']);self.event.wait(3)
 class Chat:
  status='unavailable'
  def __init__(self,*args):pass
  def run(self):pass
  def close(self):pass
 monkeypatch.setattr('worker.rolling_buffer.RollingBuffer',Buffer);monkeypatch.setattr('worker.chat_relay_client.RelayChatWatcher',Chat)
 class Client:
  running=True
  def configuration(self):return {'effective':{'running':self.running,'slots':1,'forced':[],'favorites':[],'categories':[],'platformSlots':{'twitch':1,'kick':0}},'queueAvailable':False,'triggers':default_trigger_settings()}
  def request(self,*args):return {'sources':[{'platform':'twitch','login':'one','live':True},{'platform':'kick','login':'two','live':True}]}
  def companion_heartbeat(self,data):reports.append(data)
 c=Client();r=MonitorRuntime(c,tmp_path,lambda *args:None)
 try:
  r.tick()
  for _ in range(50):
   if started:break
   time.sleep(.01)
  assert started==['one'];assert len(reports[-1]['monitoredSources'])==1
  r.tick();assert len(r.active)==1
  c.running=False;r.tick()
 finally:r.close()
 assert all(e.is_set() for f,e in r.active.values())

def test_production_monitor_does_not_fall_back_to_timed_capture_without_triggers(tmp_path,monkeypatch):
 calls=[]
 class Client:
  def configuration(self):return {'effective':{'running':True,'slots':1,'forced':[],'favorites':[],'categories':[]}}
  def request(self,*args):return {'sources':[{'platform':'twitch','login':'one','live':True}]}
  def companion_heartbeat(self,data):self.report=data
 client=Client();runtime=MonitorRuntime(client,tmp_path,lambda *args:calls.append('review'))
 monkeypatch.setattr(runtime,'_capture',lambda *args:calls.append('timed capture'))
 try:
  runtime.tick()
  for future,event in runtime.active.values():future.result(timeout=2)
  assert not calls
  assert not runtime.active
  assert client.report['errorCode']=='trigger_settings_unavailable'
 finally:runtime.close()

@pytest.mark.parametrize('spike',[False,True])
def test_quiet_buffer_is_not_reviewed_and_spike_uses_saved_clip_timing(tmp_path,monkeypatch,spike):
 opened=[];reviewed=[];timings=[]
 class Client:
  def request(self,method,path,body=None):
   assert path=='/api/worker/jobs/open';opened.append(body)
   return {'job':{'id':'a'*32,'lease':'b'*32,'source':body}}
  def report(self,*args):pass
 runtime=MonitorRuntime(Client(),tmp_path,lambda job,path,event:reviewed.append(job))
 class Buffer:
  def __init__(self,source,directory,event,on_segment,on_ready,status):
   self.on_segment=on_segment;self.on_ready=on_ready;self.parts=[(tmp_path/'part',0,40)];self.media_time=40;self.completed_at=time.monotonic();self.pending=None;self.lock=threading.Lock()
  def trigger(self,before,after,job,position):
   timings.append((before,after));self.pending=(40-before,40+after,job);return True
  def run(self):
   for _ in range(8):self.on_segment(tmp_path/'part')
   # Buffering and even detecting a cue alone must not invoke Davey.
   assert not reviewed
   if self.pending:
    start,end,job=self.pending;self.pending=None
    self.on_ready(self.parts,start,end,job)
 class Chat:
  status='disabled'
  def __init__(self,*args):pass
  def run(self):pass
  def close(self):pass
 levels=iter([-50]*7+([-10] if spike else [-50]))
 monkeypatch.setattr('worker.rolling_buffer.RollingBuffer',Buffer)
 monkeypatch.setattr('worker.chat_relay_client.RelayChatWatcher',Chat)
 monkeypatch.setattr('worker.rolling_buffer.audio_level',lambda path:next(levels))
 monkeypatch.setattr('worker.rolling_buffer.extract',lambda *args:tmp_path/'clip.mkv')
 monkeypatch.setattr(runtime,'metrics',lambda:{})
 runtime.latest={'triggers':{**default_trigger_settings(),'beforeSeconds':25,'afterSeconds':10,'speechEnabled':False,'chatEnabled':False,'chatSpikeEnabled':False},'queueAvailable':True}
 try:runtime._watch({'platform':'twitch','login':'one'},threading.Event())
 finally:runtime.close()
 assert len(opened)==int(spike)
 assert len(reviewed)==int(spike)
 assert timings==([(25,10)] if spike else [])
 if spike:assert reviewed[0]['captureCue']=='audio_rise'
