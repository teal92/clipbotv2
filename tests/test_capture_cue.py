import json,threading
from types import SimpleNamespace as NS
import pytest
from server.analysis import AnalysisService,AnalysisDenied
from server.analysis_api import AnalyzeWindow
from server.store import Store
from server.budgets import BudgetLedger

TRANSCRIPT=[{'start':0,'end':40,'text':'A complete setup and payoff.'}]
CONTEXT={'duration':40,'platform':'twitch','creator':'channel'}

class Messages:
    def __init__(self):self.calls=0;self.requests=[]
    def count_tokens(self,**kwargs):return NS(input_tokens=100)
    def create(self,**kwargs):
        self.calls+=1;self.requests.append(kwargs)
        return NS(usage=NS(input_tokens=100,output_tokens=80,cache_creation_input_tokens=0,cache_read_input_tokens=0),content=[NS(type='text',text='null')],stop_reason='end_turn')

def service(tmp_path):
    store=Store(tmp_path/'cue.db');uid=store.create_user('cue@example.com','a-good-long-password','Cue')
    store.set_coverage(uid,review_daily=45,user_monthly=6000000,scouts=12,favorites=3,categories=3,posts=20)
    store.save_preferences(uid,{'usagePreset':'balanced'})
    messages=Messages();analysis=AnalysisService(store,BudgetLedger(store,enabled=True),NS(messages=messages))
    return uid,messages,analysis

def test_accepted_capture_cue_is_optional_and_not_quality_evidence(tmp_path):
    uid,messages,analysis=service(tmp_path)
    analysis.analyze(uid,'old',TRANSCRIPT,CONTEXT)
    assert 'captureCue' not in json.loads(messages.requests[0]['messages'][0]['content'])['context']
    analysis.analyze(uid,'cue',TRANSCRIPT,{**CONTEXT,'captureCue':'chat_spike'})
    prompt=messages.requests[-1]
    assert json.loads(prompt['messages'][0]['content'])['context']['captureCue']=='chat_spike'
    assert 'not clip quality evidence' in prompt['system']
    assert 'Do not infer' in prompt['system']
    assert 'tools' not in prompt and prompt['thinking']=={'type':'disabled'}
    analysis.analyze(uid,'cue',TRANSCRIPT,{**CONTEXT,'captureCue':'chat_spike'})
    assert messages.calls==2

@pytest.mark.parametrize('invalid',['private phrase',123,True,{},['audio_rise'],'capture'])
def test_invalid_capture_cue_rejected_before_model_dispatch(tmp_path,invalid):
    uid,messages,analysis=service(tmp_path)
    with pytest.raises(AnalysisDenied):analysis.analyze(uid,'invalid',TRANSCRIPT,{**CONTEXT,'captureCue':invalid})
    assert messages.calls==0
    with pytest.raises(ValueError):AnalyzeWindow(jobId='a'*32,lease='b'*32,duration=40,transcript=TRANSCRIPT,captureCue=invalid)

@pytest.mark.parametrize('cue',[None,'manual','speech_phrase','chat_phrase','chat_spike','audio_rise'])
def test_request_accepts_only_existing_capture_cues(cue):
    assert AnalyzeWindow(jobId='a'*32,lease='b'*32,duration=40,transcript=TRANSCRIPT,captureCue=cue).captureCue==cue

@pytest.mark.parametrize('cue',[None,'audio_rise'])
def test_worker_forwards_actual_job_cue_without_fabricating_missing_context(tmp_path,monkeypatch,cue):
    from worker.processor import ClipProcessor
    monkeypatch.setattr('worker.processor.load_model',lambda _:None)
    monkeypatch.setattr('worker.processor.transcribe',lambda *args,**kwargs:TRANSCRIPT)
    monkeypatch.setattr('worker.processor.probe',lambda _:40)
    class Client:
        def request(self,method,path,body):self.body=body;return {'candidate':None}
        def report(self,*args):pass
    client=Client();processor=ClipProcessor(client,tmp_path,tmp_path,{})
    job={'id':'a'*32,'lease':'b'*32,**({'captureCue':cue} if cue else {})}
    processor.pending.acquire()
    processor.entries[job['id']]={'job':job,'path':tmp_path/'capture.mkv','event':threading.Event(),'phase':'transcribing'}
    try:
        processor._analyze(job['id'])
        assert client.body.get('captureCue')==cue
        assert ('captureCue' in client.body)==bool(cue)
        assert not any(field in client.body for field in ('interaction','audioPeakDb','chatMessages'))
    finally:processor.close()

def test_http_validates_capture_cue_before_dispatch_and_forwards_only_enum(tmp_path,monkeypatch):
    import time
    from fastapi.testclient import TestClient
    from server.app import create_app
    uid,messages,analysis=service(tmp_path);store=analysis.store
    monkeypatch.setenv('CLIPBOT_ADMIN_USER_ID',uid)
    store.accept_beta(uid)
    with store.connection() as db:db.execute("INSERT OR REPLACE INTO guards VALUES('live_test_dispatch',?)",(json.dumps({'owner':uid,'expires':time.time()+3600}),))
    token=store.connect_worker(store.new_pairing(uid));app=create_app(store,origin='http://testserver');app.state.analysis.client=NS(messages=messages)
    job=app.state.pipeline_jobs.enqueue(uid,{'platform':'twitch','login':'channel'});claim=app.state.pipeline_jobs.claim(token)
    app.state.pipeline_jobs.report(token,job,claim['lease'],{'stage':'capturing'})
    app.state.pipeline_jobs.report(token,job,claim['lease'],{'stage':'transcribing'})
    body={'jobId':job,'lease':claim['lease'],'duration':40,'transcript':TRANSCRIPT}
    headers={'Authorization':'Bearer '+token,'Origin':'http://testserver'}
    with TestClient(app) as client:
        assert client.post('/api/worker/analyze',json={**body,'captureCue':'private phrase'},headers=headers).status_code==422
        assert messages.calls==0
        assert client.post('/api/worker/analyze',json={**body,'captureCue':'manual'},headers=headers).status_code==200
    assert messages.calls==1
    assert json.loads(messages.requests[-1]['messages'][0]['content'])['context']['captureCue']=='manual'

@pytest.mark.parametrize('accepted',[False,True])
def test_runtime_attaches_cue_only_to_an_accepted_capture(tmp_path,monkeypatch,accepted):
    import time
    from worker.runtime import MonitorRuntime
    from server.trigger_settings import default_trigger_settings
    class Client:
        def request(self,*args):self.job={'id':'a'*32,'lease':'b'*32,'source':{'platform':'twitch','login':'one'}};return {'job':self.job}
        def report(self,*args):pass
    client=Client();runtime=MonitorRuntime(client,tmp_path,lambda *args:None)
    class Buffer:
        def __init__(self,source,directory,event,*args):self.parts=[(tmp_path/'part',0,40)];self.media_time=40;self.completed_at=time.monotonic();self.pending=None;self.lock=threading.Lock()
        def trigger(self,before,after,job,position):
            if accepted:self.pending=(20,60,job)
            return accepted
        def run(self):runtime.sessions[('twitch','one')]('manual')
    class Chat:
        status='disabled'
        def __init__(self,*args):pass
        def run(self):pass
        def close(self):pass
    monkeypatch.setattr('worker.rolling_buffer.RollingBuffer',Buffer)
    monkeypatch.setattr('worker.chat_relay_client.RelayChatWatcher',Chat)
    monkeypatch.setattr(runtime,'metrics',lambda:{})
    runtime.latest={'triggers':default_trigger_settings(),'queueAvailable':True}
    try:
        runtime._watch({'platform':'twitch','login':'one'},threading.Event())
        assert client.job.get('captureCue')==('manual' if accepted else None)
    finally:runtime.close()
