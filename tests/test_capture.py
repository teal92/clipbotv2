from threading import Event
from unittest.mock import Mock
import pytest
from worker.capture import capture, stream_url, CaptureError, validate_media_url

def test_capture_source_and_cdn_urls_reject_arbitrary_hosts():
    assert stream_url({'platform':'twitch','login':'channel'})=='https://www.twitch.tv/channel'
    assert validate_media_url('https://abc.ttvnw.net/live.m3u8?token=secret','twitch')
    for url in ['file:///secret','https://localhost/media','https://127.0.0.1/a','https://evil.test/media','https://ttvnw.net.evil.test/a','https://user:secret@abc.ttvnw.net/a']:
        with pytest.raises(CaptureError):validate_media_url(url,'twitch')
    with pytest.raises(CaptureError):stream_url({'platform':'twitch','login':'a;echo'})


def test_native_capture_requires_peer_verification_and_bundled_roots():
    import certifi
    from worker.capture import capture_tls_options
    for platform in ('darwin','linux'):
        assert capture_tls_options(platform) == ['-tls_verify','1','-ca_file',certifi.where()]
    assert capture_tls_options('win32') == ['-tls_verify','1']

def test_capture_pauses_before_fetch_on_low_disk_or_cancel(tmp_path):
    resolver=Mock();stop=Event();stop.set()
    with pytest.raises(CaptureError):capture({'platform':'kick','login':'channel'},tmp_path,stop,resolver=resolver)
    stop.clear()
    with pytest.raises(CaptureError):capture({'platform':'kick','login':'channel'},tmp_path,stop,resolver=resolver,disk_free=lambda _:0)
    resolver.assert_not_called()

def test_capture_cancellation_terminates_process_without_shell(tmp_path):
    stop=Event();process=Mock();process.poll.return_value=None
    def spawn(args,**kwargs):
        assert kwargs.get('shell',False) is False
        assert '-t' in args and args[args.index('-t')+1]=='120'
        assert args[args.index('-protocol_whitelist')+1]=='https,tls,tcp,crypto'
        assert args[args.index('-tls_verify')+1]=='1'
        stop.set();return process
    with pytest.raises(CaptureError):capture({'platform':'twitch','login':'channel'},tmp_path,stop,resolver=lambda _: 'https://abc.ttvnw.net/live.m3u8',popen=spawn,disk_free=lambda _:10**12)
    process.kill.assert_called_once()


def test_monitor_runs_two_sources_and_stop_cancels_both(tmp_path):
    import time
    from worker.runtime import MonitorRuntime
    class Client:
        running=True
        def configuration(self):return {'effective':{'running':self.running,'slots':2,'forced':[],'favorites':[],'categories':[]}}
        def request(self,method,path,body=None):
            if path.endswith('/discovery'):return {'sources':[{'platform':'twitch','login':'one','live':True},{'platform':'kick','login':'two','live':True}]}
            return {'job':{'id':body['login'],'lease':'lease','source':body}}
        def report(self,*args):pass
        def heartbeat(self):pass
    started=[];stopped=[]
    def ingest(source,directory,event,**kwargs):
        started.append(source['login']);event.wait(2);stopped.append(source['login']);raise CaptureError('cancelled')
    client=Client();runtime=MonitorRuntime(client,tmp_path,lambda *args:None,capture_function=ingest)
    runtime.tick()
    for _ in range(100):
        if len(started)==2:break
        time.sleep(.01)
    assert set(started)=={'one','two'}
    client.running=False;runtime.tick();runtime.close()
    assert set(stopped)=={'one','two'}


def test_category_monitor_advances_after_completed_window(tmp_path):
    import time
    from worker.runtime import MonitorRuntime
    class Client:
        def configuration(self):return {'effective':{'running':True,'slots':1,'forced':[],'favorites':[],'categories':[]}}
        def request(self,method,path,body=None):
            if path.endswith('/discovery'):return {'sources':[{'platform':'twitch','login':v,'live':True} for v in ('one','two','three')]}
            return {'job':{'id':body['login'],'lease':'lease','source':body}}
        def report(self,*args):pass
        def heartbeat(self):pass
    seen=[]
    def ingest(source,directory,event,**kwargs):seen.append(source['login']);return directory/'capture.mkv'
    runtime=MonitorRuntime(Client(),tmp_path,lambda *args:None,capture_function=ingest,hardware_slots=1)
    try:
        for _ in range(20):runtime.tick();time.sleep(.02)
        assert set(seen)=={'one','two','three'}
    finally:runtime.close()

def test_capture_quality_gate_does_not_bypass_structural_bounds():
 from worker.capture import capture_quality_allowed
 assert capture_quality_allowed(60,120,'balanced')
 assert not capture_quality_allowed(60,120,'strict')
 assert capture_quality_allowed(20,120,'review')
 assert not capture_quality_allowed(10,120,'review')

def test_runtime_does_not_allocate_two_slots_to_retained_forced_category(tmp_path):
 import threading
 from concurrent.futures import Future
 from worker.runtime import MonitorRuntime
 cfg={'running':True,'slots':2,'forced':[],'favorites':[],'categories':[],'forcedCategories':[{'platform':'twitch','id':'1','name':'First'},{'platform':'twitch','id':'2','name':'Second'}]}
 class Client:
  def configuration(self):return {'effective':cfg}
  def heartbeat(self):pass
 client=Client();runtime=MonitorRuntime(client,tmp_path,lambda *args:None,capture_function=lambda *args,**kwargs:None)
 runtime.last_discovery=__import__('time').monotonic()
 runtime.sources=[{'platform':'twitch','login':login,'live':True,'categoryId':category,'viewers':viewers} for login,category,viewers in [('active','1',100),('duplicate','1',90),('second','2',50)]]
 runtime.active[('twitch','active')]=(Future(),threading.Event())
 class Pool:
  def submit(self,*args):return Future()
  def shutdown(self,**kwargs):pass
 runtime.pool.shutdown(wait=True);runtime.pool=Pool()
 runtime.tick();assert set(runtime.active)=={('twitch','active'),('twitch','second')}
 runtime.close()
