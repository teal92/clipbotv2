import pytest
from worker import interaction

def test_real_samples_are_bounded_and_missing_audio_is_not_silence():
    window=interaction.InteractionWindow()
    for n in range(30):
        window.observe(n*5+100, chat_connected=True)
        window.audio(-42+n/10, n*5+100)
    samples=window.snapshot()["samples"]
    assert len(samples)==24
    assert samples[-1]["audioDb"]==-39.1
    assert samples[-1]["chatMessages"]==0
    window.observe(250, chat_connected=False)
    assert window.snapshot()["samples"][-1]["chatMessages"] is None
    assert window.snapshot()["samples"][-1]["audioDb"] is None

def test_only_numeric_chat_and_cues_leave_window():
    window=interaction.InteractionWindow()
    window.chat(101);window.chat(102);window.cue("speech_phrase",103)
    row=window.snapshot()["samples"][0]
    assert row=={"at":100,"audioDb":None,"chatMessages":2,"cues":["speech_phrase"]}
    window.audio(float("nan"),103)
    assert window.snapshot()["samples"][0]["audioDb"] is None

def test_validation_rejects_unbounded_nonfinite_and_text_payloads():
    from server.interaction import validate_interaction
    good={"samples":[{"at":100,"audioDb":None,"chatMessages":0,"cues":[]}]}
    validate_interaction(good, now=150)
    for bad in ({"samples":good["samples"]*25},{"samples":[{**good["samples"][0],"audioDb":float("nan")}]},{"samples":[{**good["samples"][0],"text":"private"}]}):
        with pytest.raises(ValueError):validate_interaction(bad,now=150)

def test_delayed_chat_updates_original_bucket_without_becoming_current_activity():
    window=interaction.InteractionWindow()
    window.observe(100,chat_connected=True)
    window.observe(105,chat_connected=True)
    window.chat(101)
    assert window.snapshot()['samples'][0]['chatMessages']==1
    assert window.snapshot()['samples'][1]['chatMessages']==0

def test_authenticated_heartbeat_preserves_real_samples_and_rejects_text(tmp_path):
    import time
    from server.store import Store
    from server.scouts import ScoutStore
    from server.companion import CompanionStore
    store=Store(tmp_path/'interaction.db')
    uid=store.create_user('chart@example.com','a-good-long-password','Chart')
    store.set_coverage(uid,review_daily=45,user_monthly=6000000,scouts=2,favorites=2,categories=2,posts=20)
    token=store.connect_worker(store.new_pairing(uid))
    scouts=ScoutStore(store);companion=CompanionStore(store)
    scouts.save(uid,{'running':True,'slots':1,'forced':[],'favorites':[],'categories':[]})
    window=interaction.InteractionWindow();window.audio(-36,time.time());window.chat(time.time())
    source={'platform':'twitch','login':'one','state':'monitoring','started':time.time(),'chatStatus':'connected','speechStatus':'waiting','cueStatus':'watching_for_cues','interaction':window.snapshot()}
    report={'ready':True,'monitoring':True,'acknowledgedRevision':'','hardwareSlots':2,'activeScouts':1,'errorCode':None,'monitoredSources':[source]}
    companion.report(token,report)
    assert companion.status(uid)['monitoredSources'][0]['interaction']==window.snapshot()
    source['interaction']['samples'][0]['text']='private transcript'
    with pytest.raises(ValueError):companion.report(token,report)

def test_worker_uses_existing_audio_sampling_and_never_enables_disabled_audio(tmp_path,monkeypatch):
    import time
    from threading import Event
    from worker.runtime import MonitorRuntime
    from server.trigger_settings import default_trigger_settings
    measured=[]
    class Buffer:
        def __init__(self,source,directory,event,segment,ready,status):
            self.event=event;self.segment=segment;self.media_time=5;self.pending=None;self.parts=[];self.completed_at=time.monotonic()
        def run(self):self.segment('existing-segment');self.event.wait(5.2)
    class Chat:
        status='connected'
        def __init__(self,*args):pass
        def run(self):pass
        def close(self):pass
    monkeypatch.setattr('worker.rolling_buffer.RollingBuffer',Buffer)
    monkeypatch.setattr('worker.chat_relay_client.RelayChatWatcher',Chat)
    monkeypatch.setattr('worker.rolling_buffer.audio_level',lambda path:measured.append(path) or -27)
    runtime=MonitorRuntime(object(),tmp_path,lambda *args:None)
    runtime.latest={'triggers':{**default_trigger_settings(),'audioEnabled':True,'speechEnabled':False,'chatEnabled':True},'queueAvailable':False}
    try:
        runtime._watch({'platform':'twitch','login':'one'},Event())
        rows=runtime.states[('twitch','one')]['interaction']['samples']
        assert measured==['existing-segment']
        assert any(row['audioDb']==-27 for row in rows)
        runtime.latest['triggers']['audioEnabled']=False
        runtime._watch({'platform':'twitch','login':'two'},Event())
        rows=runtime.states[('twitch','two')]['interaction']['samples']
        assert all(row['audioDb'] is None for row in rows)
        assert measured==['existing-segment']
    finally:runtime.close()

def test_forty_scout_full_windows_cross_old_limit_and_remain_authenticated(tmp_path):
    import json,time
    from fastapi.testclient import TestClient
    from server.app import create_app
    from server.store import Store
    from server.scouts import ScoutStore
    from server.companion import CompanionStore
    store=Store(tmp_path/'full-heartbeat.db')
    uid=store.create_user('full-chart@example.com','a-good-long-password','Full chart')
    store.set_coverage(uid,review_daily=45,user_monthly=6000000,scouts=40,favorites=2,categories=2,posts=20)
    token=store.connect_worker(store.new_pairing(uid))
    ScoutStore(store).save(uid,{'running':True,'slots':40,'forced':[],'favorites':[],'categories':[]})
    now=int(time.time()//5)*5
    samples=[{'at':now-115+n*5,'audioDb':-27.5,'chatMessages':100000,'cues':['manual','speech_phrase','chat_phrase','chat_spike','audio_rise','capture']} for n in range(24)]
    sources=[{'platform':'twitch','login':f'scout{n}','state':'monitoring','started':now-200,'chatStatus':'connected','speechStatus':'active','cueStatus':'watching_for_cues','interaction':{'samples':samples}} for n in range(40)]
    report={'ready':True,'monitoring':True,'acknowledgedRevision':'','hardwareSlots':40,'activeScouts':40,'errorCode':None,'version':'0.2.7-beta','monitoredSources':sources}
    content=json.dumps(report).encode()
    assert 16384<len(content)<262144
    headers={'Authorization':'Bearer '+token,'Content-Type':'application/json','Origin':'http://testserver'}
    with TestClient(create_app(store,origin='http://testserver')) as client:
        assert client.post('/api/worker/companion-heartbeat',content=content,headers={'Content-Type':'application/json','Origin':'http://testserver'}).status_code==401
        assert client.post('/api/worker/companion-heartbeat',content=content,headers=headers).status_code==200
        returned=CompanionStore(store).status(uid)['monitoredSources']
        assert len(returned)==40
        assert returned[-1]['interaction']['samples']==samples
        invalid={**report,'monitoredSources':[dict(sources[0],interaction={'samples':samples+[samples[-1]]})]}
        assert client.post('/api/worker/companion-heartbeat',json=invalid,headers=headers).status_code==401
        # Exactly the allowed size is accepted; the byte after it is rejected.
        padded=content+b' '*(262144-len(content))
        assert client.post('/api/worker/companion-heartbeat',content=padded,headers=headers).status_code==200
        assert client.post('/api/worker/companion-heartbeat',content=padded+b' ',headers=headers).status_code==413
        # Chunked transfer has no Content-Length and must enforce the same bound.
        assert client.post('/api/worker/companion-heartbeat',content=iter([padded,b' ']),headers=headers).status_code==413
        assert client.post('/api/companion/control',content=b' '*16385,headers=headers).status_code==413
