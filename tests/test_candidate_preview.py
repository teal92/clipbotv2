import json,threading,time
import pytest
from fastapi.testclient import TestClient
from server.app import create_app
from server.store import Store
from worker.local_app import create_local_app
from worker.review_preview import review_preview
from server.display_text import display_text

def test_feedback_owner_proves_older_candidate_and_preview_device(tmp_path):
    from server.store import token_hash
    store=Store(tmp_path/'feedback-owner.db');uid=store.create_user('owner-old@example.com','long-password-for-test','Owner')
    app=create_app(store,origin='http://testserver');token=store.connect_worker(store.new_pairing(uid));old='f'*32
    other=store.create_user('foreign-old@example.com','long-password-for-test','Other');foreign=store.connect_worker(store.new_pairing(other))
    with store.connection() as db:
        for n in range(106):
            job=old if n==0 else f'{n:032x}'
            db.execute('INSERT INTO pipeline_jobs(id,user_id,source,stage,created,updated) VALUES(?,?,?,?,?,?)',(job,uid,json.dumps({'platform':'twitch','login':'old'}),'published',n,n))
        db.execute('INSERT INTO candidates VALUES(?,?,?)',(old,uid,json.dumps({'id':old})))
        db.execute('INSERT INTO candidate_previews VALUES(?,?,?,?,?)',(uid,old,token_hash(token),'a'*64,0))
    with TestClient(app) as client:
        headers={'Origin':'http://testserver','Authorization':'Bearer '+token}
        assert old not in [j['id'] for j in client.get('/api/worker/state',headers=headers).json()['jobs']]
        response=client.get('/api/worker/feedback-owner?candidateId='+old,headers=headers)
        assert response.status_code==200
        assert response.json()=={'userId':uid,'candidateId':old}
        assert client.get('/api/worker/feedback-owner?candidateId='+old,headers={**headers,'Authorization':'Bearer '+foreign}).status_code==404
        assert client.get('/api/worker/feedback-owner?candidateId=../private',headers=headers).status_code==422
        with store.connection() as db:db.execute('UPDATE candidate_previews SET device=? WHERE job_id=?',(token_hash(foreign),old))
        assert client.get('/api/worker/feedback-owner?candidateId='+old,headers=headers).status_code==404

def test_candidate_preview_requires_owner_device_and_review_lease(tmp_path):
    store=Store(tmp_path/'preview.db');uid=store.create_user('preview@example.com','long-password-for-test','Preview')
    app=create_app(store,origin='http://testserver');jobs=app.state.pipeline_jobs
    token=store.connect_worker(store.new_pairing(uid));job=jobs.enqueue(uid,{'platform':'twitch','login':'streamer'});claim=jobs.claim(token)
    with store.connection() as db:
        db.execute("UPDATE pipeline_jobs SET stage='review' WHERE id=?",(job,))
        db.execute('INSERT INTO candidates VALUES(?,?,?)',(job,uid,json.dumps({'id':job,'creator':'streamer','platform':'twitch'})))
    other=store.create_user('other-preview@example.com','long-password-for-test','Other');foreign=store.connect_worker(store.new_pairing(other));body={'jobId':job,'lease':claim['lease'],'previewToken':'a'*64}
    with TestClient(app) as client:
        headers={'Origin':'http://testserver','Authorization':'Bearer '+foreign}
        assert client.post('/api/worker/candidate-preview-ready',json=body,headers=headers).status_code==409
        headers['Authorization']='Bearer '+token
        assert client.post('/api/worker/candidate-preview-ready',json={**body,'previewToken':'../capture.mkv'},headers=headers).status_code==422
        assert client.post('/api/worker/candidate-preview-ready',json=body,headers=headers).status_code==200
        assert jobs.snapshot(uid)[0]['stage']=='review'
        with store.connection() as db:
            for n in range(105):db.execute('INSERT INTO pipeline_jobs(id,user_id,source,stage,created,updated) VALUES(?,?,?,?,?,?)',(f'{n:032x}',uid,json.dumps({'platform':'twitch','login':'oldfailed'}),'failed',time.time()+n,time.time()+n))
        recovered=client.get('/api/worker/state',headers=headers).json()['jobs']
        assert recovered[0]['id']==job and recovered[0]['candidate']
        raw,_=store.new_session(uid);client.cookies.set('clipbot_session',raw)
        workspace=client.get('/api/workspace').json()
        assert workspace['candidates'][0]['previewUrl']=='http://127.0.0.1:8767/preview/'+'a'*64
        assert workspace['ready']==[] and workspace['publications']==[]
        raw_other,_=store.new_session(other);client.cookies.set('clipbot_session',raw_other)
        assert client.get('/api/workspace').json()['candidates']==[]
        store.revoke_workers(uid);client.cookies.set('clipbot_session',raw)
        assert 'previewUrl' not in client.get('/api/workspace').json()['candidates'][0]

def test_review_preview_never_serves_raw_capture_or_unregistered_files(tmp_path):
    app=create_local_app('https://clipbot.example',tmp_path,start_runtime=False)
    directory=tmp_path/('a'*32);directory.mkdir();preview=directory/'candidate-preview.mp4';preview.write_bytes(b'preview');capture=directory/'capture.mkv';capture.write_bytes(b'private')
    app.state.previews['b'*64]=preview;app.state.previews['c'*64]=capture
    with TestClient(app,base_url='http://127.0.0.1:8767',client=('127.0.0.1',32100)) as client:
        assert client.get('/preview/'+'b'*64).status_code==200
        assert client.get('/media/'+'b'*64).status_code==200
        assert client.get('/media/'+'c'*64).status_code==404
        assert client.get('/media/'+'d'*64).status_code==404
    for bounds in ({'start':0,'end':14},{'start':-1,'end':30},{'start':0,'end':306}):
        with pytest.raises(ValueError):review_preview(bounds,capture,threading.Event())

def test_display_repair_preserves_clean_unicode_and_repairs_legacy_mojibake():
    for clean in ('São Paulo','Türkçe','日本語','Emoji 😂'):
        assert display_text(clean)==clean
    broken='Win 😂'.encode('utf-8').decode('cp1252')
    assert display_text(broken)=='Win 😂'


def test_mobile_artifact_can_be_prepared_in_review_without_approval(tmp_path):
    store=Store(tmp_path/'vertical.db');uid=store.create_user('vertical@example.com','long-password-for-test','Vertical')
    app=create_app(store,origin='http://testserver');jobs=app.state.pipeline_jobs;token=store.connect_worker(store.new_pairing(uid))
    job=jobs.enqueue(uid,{'platform':'kick','login':'streamer'});claim=jobs.claim(token)
    with store.connection() as db:db.execute("UPDATE pipeline_jobs SET stage='review' WHERE id=?",(job,))
    artifact={'sha256':'a'*64,'sizeBytes':1024,'duration':20,'width':1080,'height':1920,'framing':'blurred_fit'}
    headers={'Origin':'http://testserver','Authorization':'Bearer '+token}
    with TestClient(app) as c:
        result=c.post('/api/worker/render-ready',json={'jobId':job,'lease':claim['lease'],'artifact':artifact,'previewToken':'b'*64},headers=headers)
        assert result.status_code==200 and result.json()['stage']=='review'
        assert jobs.snapshot(uid)[0]['stage']=='review'
        assert app.state.publication.snapshot(uid)==[]
        with store.connection() as db:
            assert db.execute('SELECT token FROM candidate_previews WHERE user_id=? AND job_id=?',(uid,job)).fetchone()[0]=='b'*64
            assert db.execute('SELECT data FROM clip_artifacts WHERE user_id=? AND clip_id=?',(uid,job)).fetchone()

def test_display_repair_handles_mixed_clean_unicode_and_legacy_text():
    broken='Win 😂'.encode('utf-8').decode('cp1252')
    assert display_text('日本語 '+broken)=='日本語 Win 😂'


def test_pipeline_approval_waits_for_mobile_preview(tmp_path):
    store=Store(tmp_path/'approval.db');uid=store.create_user('approve@example.com','long-password-for-test','Approve')
    app=create_app(store,origin='http://testserver');token=store.connect_worker(store.new_pairing(uid));job=app.state.pipeline_jobs.enqueue(uid,{'platform':'kick','login':'one'});claim=app.state.pipeline_jobs.claim(token)
    with store.connection() as db:
        db.execute("UPDATE pipeline_jobs SET stage='review' WHERE id=?",(job,));db.execute('INSERT INTO candidates VALUES(?,?,?)',(job,uid,json.dumps({'id':job,'creator':'one','platform':'kick'})))
    store.accept_beta(uid);raw,_=store.new_session(uid)
    with TestClient(app) as c:
        c.cookies.set('clipbot_session',raw);csrf=c.get('/api/account').json()['csrfToken'];h={'Origin':'http://testserver','X-CSRF-Token':csrf};choice={'candidate_id':job,'decision':'approve','reasons':['Funny'],'justification':'Good moment'}
        assert c.post('/api/reviews',json=choice,headers=h).status_code==409
        body={'jobId':job,'lease':claim['lease'],'artifact':{'sha256':'a'*64,'sizeBytes':1024,'duration':20,'width':1080,'height':1920,'framing':'blurred_fit'},'previewToken':'b'*64}
        assert c.post('/api/worker/render-ready',json=body,headers={'Origin':'http://testserver','Authorization':'Bearer '+token}).status_code==200
        assert c.post('/api/reviews',json=choice,headers=h).status_code==200


def test_edited_media_and_learning_preserve_capability_and_owner_checks(tmp_path):
    from types import SimpleNamespace
    app=create_local_app('https://clipbot.example',tmp_path,start_runtime=False)
    job='a'*32;uid='b'*32;token='c'*64
    directory=tmp_path/job;directory.mkdir()
    edited=directory/('clip-edit-'+'d'*32+'.mp4');edited.write_bytes(b'edited')
    app.state.previews[token]=edited
    app.state.worker['client']=SimpleNamespace(token='paired',close=lambda:None,request=lambda *args:{'userId':uid,'jobs':[{'id':job}]})
    headers={'Origin':'https://clipbot.example'}
    with TestClient(app,base_url='http://127.0.0.1:8767',client=('127.0.0.1',32100)) as client:
        assert client.get('/preview/'+token).status_code==200
        assert client.get('/media/'+token).content==b'edited'
        body={'userId':uid,'candidateId':job,'decision':'approve','reasons':[],'justification':''}
        assert client.post('/feedback/'+token,json=body,headers=headers).status_code==200
        assert client.get('/feedback/'+token,headers=headers).json()['feedback']['decision']=='approve'
        assert client.post('/feedback/'+token,json={**body,'userId':'e'*32},headers=headers).status_code==403
        invalid=directory/'clip-edit-untrusted.mp4';invalid.write_bytes(b'bad');app.state.previews['f'*64]=invalid
        assert client.get('/media/'+'f'*64).status_code==404
