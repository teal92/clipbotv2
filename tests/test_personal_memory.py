import importlib
import json
from fastapi.testclient import TestClient
from worker.local_app import create_local_app

UID='a'*32
CID='b'*32
TOKEN='c'*64

def test_memory_keeps_notes_local_and_only_summarizes_confirmed_account_reviews(tmp_path):
    assert importlib.util.find_spec('worker.personal_memory') is not None
    from worker.personal_memory import PersonalMemory
    memory=PersonalMemory(tmp_path,'https://clipbot.example',UID)
    memory.record(CID,'approve',['Funny'],'PRIVATE NOTE')
    assert memory.summary()['reviewCount']==0
    memory.confirm([{'candidateId':CID,'decision':'approve'}])
    assert memory.summary()=={'schemaVersion':1,'reviewCount':1,'approveReasons':{'Funny':1},'rejectReasons':{}}
    assert 'PRIVATE NOTE' not in json.dumps(memory.summary())
    assert PersonalMemory(tmp_path,'https://clipbot.example','d'*32).summary()['reviewCount']==0
    assert PersonalMemory(tmp_path,'https://other.example',UID).summary()['reviewCount']==0
    memory.record(CID,'reject',['Needs context'],'CORRECTION')
    assert memory.summary()['reviewCount']==0
    memory.confirm([{'candidateId':CID,'decision':'reject'}])
    assert memory.summary()['rejectReasons']=={'Needs context':1}

def test_memory_caps_history_and_summary(tmp_path):
    assert importlib.util.find_spec('worker.personal_memory') is not None
    from worker.personal_memory import PersonalMemory
    memory=PersonalMemory(tmp_path,'https://clipbot.example',UID)
    for index in range(2002):
        cid=f'{index:032x}'
        memory.record(cid,'approve',['Funny'],'')
        memory.confirm([{'candidateId':cid,'decision':'approve'}])
    import sqlite3
    with sqlite3.connect(memory.path) as db:
        assert db.execute('SELECT COUNT(*) FROM reviews').fetchone()[0]==2000
    assert memory.summary()['reviewCount']==200

def test_local_feedback_requires_origin_capability_and_verified_account(tmp_path):
    app=create_local_app('https://clipbot.example',tmp_path/'jobs',start_runtime=False)
    directory=tmp_path/'jobs'/CID;directory.mkdir();preview=directory/'clip.mp4';preview.write_bytes(b'clip')
    app.state.previews[TOKEN]=preview
    class Client:
        token='paired'
        def request(self,*args):return {'userId':UID,'jobs':[{'id':CID}],'reviews':[]}
        def close(self):pass
    app.state.worker['client']=Client()
    body={'userId':UID,'candidateId':CID,'decision':'approve','reasons':['Funny'],'justification':'LOCAL ONLY'}
    with TestClient(app,base_url='http://127.0.0.1:8767',client=('127.0.0.1',32100)) as client:
        allowed={'Origin':'https://clipbot.example'}
        result=client.post('/feedback/'+TOKEN,json=body,headers=allowed)
        assert result.status_code==200
        assert result.json()['ok'] is True
        assert client.post('/feedback/'+TOKEN,json=body,headers={'Origin':'https://evil.test'}).status_code==403
        assert client.post('/feedback/'+'e'*64,json=body,headers=allowed).status_code==404
        assert client.post('/feedback/'+TOKEN,json={**body,'userId':'f'*32},headers=allowed).status_code==403
        assert client.post('/feedback/'+TOKEN,json={**body,'candidateId':'f'*32},headers=allowed).status_code==403
        assert client.post('/feedback/'+TOKEN,json={**body,'policy':'execute'},headers=allowed).status_code==422
        assert client.post('/feedback/'+TOKEN,content=b'x'*8193,headers=allowed).status_code==413
        assert client.post('/pair',json={'code':'x'*24},headers=allowed).status_code==403
        options=client.options('/feedback/'+TOKEN,headers={**allowed,'Access-Control-Request-Method':'POST','Access-Control-Request-Headers':'content-type'})
        assert options.status_code==204
        assert options.headers['Access-Control-Allow-Origin']=='https://clipbot.example'
        assert client.options('/feedback/'+TOKEN,headers={'Origin':'https://evil.test','Access-Control-Request-Method':'POST'}).status_code==403
        import hashlib,hmac,time
        receipt={'candidateId':CID,'userId':UID,'decision':'approve','issuedAt':int(time.time())}
        receipt['signature']=hmac.new(hashlib.sha256(b'paired').digest(),json.dumps(receipt,sort_keys=True,separators=(',',':')).encode(),hashlib.sha256).hexdigest()
        result=client.post('/feedback/'+TOKEN+'/confirm',json={'receipt':receipt},headers=allowed)
        assert result.status_code==200
        assert result.json()['memorySummary']['approveReasons']=={'Funny':1}
        assert client.get('/feedback/'+TOKEN,headers=allowed).json()['feedback']['justification']=='LOCAL ONLY'
        assert client.post('/feedback/'+TOKEN+'/confirm',json={'receipt':{**receipt,'signature':'f'*64}},headers=allowed).status_code==403
        assert client.get('/feedback/'+TOKEN,headers={'Origin':'https://evil.test'}).status_code==403
        assert client.post('/feedback/'+TOKEN,json={**body,'decision':'reject'},headers=allowed).status_code==200
        assert client.post('/feedback/'+TOKEN+'/confirm',json={'receipt':receipt},headers=allowed).status_code==409
        assert client.get('/feedback/'+TOKEN,headers=allowed).json()['feedback']['confirmed'] is False

def test_feedback_rejects_nonloopback_and_offline_account_verification(tmp_path):
    app=create_local_app('https://clipbot.example',tmp_path/'jobs',start_runtime=False)
    directory=tmp_path/'jobs'/CID;directory.mkdir();preview=directory/'clip.mp4';preview.write_bytes(b'clip')
    app.state.previews[TOKEN]=preview
    class Client:
        token='paired'
        def request(self,*args):raise RuntimeError('offline')
        def close(self):pass
    app.state.worker['client']=Client()
    body={'userId':UID,'candidateId':CID,'decision':'approve','reasons':['Funny'],'justification':'LOCAL ONLY'}
    with TestClient(app,base_url='http://127.0.0.1:8767',client=('127.0.0.1',32100)) as client:
        assert client.post('/feedback/'+TOKEN,json=body,headers={'Origin':'https://clipbot.example'}).status_code==409
    with TestClient(app,base_url='http://127.0.0.1:8767',client=('192.0.2.1',32100)) as client:
        assert client.post('/feedback/'+TOKEN,json=body,headers={'Origin':'https://clipbot.example'}).status_code==403

def test_feedback_reads_cache_owned_jobs_and_reverify_changed_pairing(tmp_path):
    app=create_local_app('https://clipbot.example',tmp_path/'jobs',start_runtime=False)
    directory=tmp_path/'jobs'/CID;directory.mkdir();preview=directory/'clip.mp4';preview.write_bytes(b'clip')
    app.state.previews[TOKEN]=preview
    class Client:
        token='first-pairing'
        calls=0
        uid=UID
        def request(self,*args):
            self.calls+=1
            return {'userId':self.uid,'jobs':[{'id':CID}]}
        def close(self):pass
    paired=Client();app.state.worker['client']=paired
    with TestClient(app,base_url='http://127.0.0.1:8767',client=('127.0.0.1',32100)) as client:
        headers={'Origin':'https://clipbot.example'}
        for _ in range(3):assert client.get('/feedback/'+TOKEN,headers=headers).status_code==200
        assert paired.calls==1
        paired.token='second-pairing';paired.uid='f'*32
        assert client.get('/feedback/'+TOKEN,headers=headers).status_code==200
        assert paired.calls==2
        body={'userId':UID,'candidateId':CID,'decision':'approve','reasons':['Funny']}
        assert client.post('/feedback/'+TOKEN,json=body,headers=headers).status_code==403
        assert paired.calls==3

def test_feedback_reads_older_owned_candidate_with_bounded_proof_and_caches(tmp_path):
    app=create_local_app('https://clipbot.example',tmp_path/'jobs',start_runtime=False)
    directory=tmp_path/'jobs'/CID;directory.mkdir();preview=directory/'clip.mp4';preview.write_bytes(b'clip');app.state.previews[TOKEN]=preview
    second='d'*32;second_token='e'*64;other=tmp_path/'jobs'/second;other.mkdir();(other/'clip.mp4').write_bytes(b'clip');app.state.previews[second_token]=other/'clip.mp4'
    class Client:
        token='paired'
        calls=[]
        def request(self,method,path):
            self.calls.append(path)
            if path=='/api/worker/state':return {'userId':UID,'jobs':[]}
            return {'userId':UID,'candidateId':path.rsplit('=',1)[-1]}
        def close(self):pass
    paired=Client();app.state.worker['client']=paired
    with TestClient(app,base_url='http://127.0.0.1:8767',client=('127.0.0.1',32100)) as client:
        headers={'Origin':'https://clipbot.example'}
        for _ in range(3):assert client.get('/feedback/'+TOKEN,headers=headers).status_code==200
        assert paired.calls==['/api/worker/state','/api/worker/feedback-owner?candidateId='+CID]
        assert client.get('/feedback/'+second_token,headers=headers).status_code==200
        assert client.get('/feedback/'+TOKEN,headers=headers).status_code==200
        assert paired.calls==['/api/worker/state','/api/worker/feedback-owner?candidateId='+CID,'/api/worker/feedback-owner?candidateId='+second]

@__import__('pytest').mark.parametrize('consented',[False,True])
def test_processor_binds_verified_local_memory_without_exporting_notes(tmp_path,monkeypatch,consented):
    import threading
    from worker.processor import ClipProcessor
    from worker.personal_memory import PersonalMemory
    monkeypatch.setattr('worker.processor.load_model',lambda _:None)
    monkeypatch.setattr('worker.processor.probe',lambda _:30)
    monkeypatch.setattr('worker.processor.transcribe',lambda *a,**k:[{'start':0,'end':30,'text':'hello'}])
    class Client:
        origin='https://clipbot.example'
        token='paired'
        analyzed=None
        def request(self,method,path,body=None):
            if path=='/api/worker/state':return {'userId':UID,'jobs':[],'publications':[],'davey':{'personalContext':consented,'revision':1}}
            if path=='/api/worker/analyze':self.analyzed=body;return {'candidate':None}
        def report(self,*a):pass
    root=tmp_path/'jobs';root.mkdir();directory=root/CID;directory.mkdir()
    memory=PersonalMemory(tmp_path/'personal-memory','https://clipbot.example',UID)
    memory.record('d'*32,'approve',['Funny'],'PRIVATE');memory.confirm([{'candidateId':'d'*32,'decision':'approve'}])
    client=Client();processor=ClipProcessor(client,root,tmp_path,{})
    processor.pending.acquire();processor.entries[CID]={'job':{'id':CID,'lease':'e'*32},'path':directory/'capture.mkv','event':threading.Event(),'phase':'transcribing'}
    try:
        processor.tick();processor._analyze(CID)
        assert processor.personal_memory.summary()=={'schemaVersion':1,'reviewCount':1,'approveReasons':{'Funny':1},'rejectReasons':{}}
        if consented:
            assert client.analyzed['personalPreferences']==memory.summary()
            assert client.analyzed['personalPreferencesRevision']==1
        else:assert 'personalPreferences' not in client.analyzed
        assert 'PRIVATE' not in json.dumps(client.analyzed)
        processor._bind_memory({'userId':'e'*32})
        assert processor.personal_memory.summary()['reviewCount']==0
    finally:processor.close()
