import json
import pytest
from fastapi.testclient import TestClient
from server.app import create_app
from server.store import Store


def setup_edit(tmp_path):
    store=Store(tmp_path/'edit.db');uid=store.create_user('edit@example.com','long-password-for-test','Editor')
    app=create_app(store,origin='http://testserver')
    # Register separately so this regression also tests the standalone router contract.
    token=store.connect_worker(store.new_pairing(uid));jobs=app.state.pipeline_jobs
    job=jobs.enqueue(uid,{'platform':'twitch','login':'streamer'});claim=jobs.claim(token)
    candidate={'id':job,'start':10,'end':50,'title':'Original','caption':'Original description','duration':'40s'}
    with store.connection() as db:
        db.execute("UPDATE pipeline_jobs SET stage='review' WHERE id=?",(job,))
        db.execute('INSERT INTO candidates VALUES(?,?,?)',(job,uid,json.dumps(candidate)))
    headers={'Origin':'http://testserver','Authorization':'Bearer '+token}
    artifact={'sha256':'a'*64,'sizeBytes':1024,'duration':40,'width':1080,'height':1920,'framing':'blurred_fit'}
    client=TestClient(app)
    assert client.post('/api/worker/render-ready',json={'jobId':job,'lease':claim['lease'],'artifact':artifact,'previewToken':'b'*64},headers=headers).status_code==200
    body={'jobId':job,'lease':claim['lease'],'previewToken':'b'*64,'title':'Edited title','description':'Edited description','start':15,'end':35}
    return store,uid,client,headers,body,artifact


def test_edits_invalidate_approval_until_verified_trim_is_complete(tmp_path):
    store,uid,c,h,body,artifact=setup_edit(tmp_path)
    started=c.post('/api/worker/clip-edits/begin',json=body,headers=h)
    assert started.status_code==200
    edit=started.json()
    assert edit['candidate']['start']==15 and edit['candidate']['end']==35
    with store.connection() as db:
        assert db.execute('SELECT stage FROM pipeline_jobs WHERE id=?',(body['jobId'],)).fetchone()[0]=='editing'
        assert db.execute('SELECT COUNT(*) FROM clip_artifacts WHERE clip_id=?',(body['jobId'],)).fetchone()[0]==1
    assert c.post('/api/worker/clip-edits/begin',json=body,headers=h).status_code==409
    complete={'jobId':body['jobId'],'editId':edit['editId'],'artifact':artifact,'previewToken':'c'*64}
    assert c.post('/api/worker/clip-edits/complete',json=complete,headers=h).status_code==422
    complete['artifact']={**artifact,'duration':20,'sha256':'d'*64}
    assert c.post('/api/worker/clip-edits/complete',json=complete,headers=h).status_code==200
    # A lost HTTP response can safely retry completion without another render or job.
    assert c.post('/api/worker/clip-edits/complete',json=complete,headers=h).status_code==200
    with store.connection() as db:
        saved=json.loads(db.execute('SELECT data FROM candidates WHERE id=?',(body['jobId'],)).fetchone()[0])
        assert (saved['title'],saved['caption'],saved['start'],saved['end'])==('Edited title','Edited description',15,35)
        assert db.execute('SELECT COUNT(*) FROM pipeline_jobs').fetchone()[0]==1
        assert db.execute('SELECT stage FROM pipeline_jobs WHERE id=?',(body['jobId'],)).fetchone()[0]=='review'


@pytest.mark.parametrize('fields',[{'start':9},{'end':51},{'start':True},{'start':float('inf')},{'end':20},{'title':'x'*151},{'description':'x'*1001}])
def test_clip_edits_reject_invalid_ranges_and_unbounded_text(tmp_path,fields):
    _,_,c,h,body,_=setup_edit(tmp_path)
    response=c.post('/api/worker/clip-edits/begin',json={**body,**fields},headers=h) if fields.get('start')!=float('inf') else c.post('/api/worker/clip-edits/begin',content=json.dumps({**body,**fields}),headers={**h,'Content-Type':'application/json'})
    assert response.status_code==422


def test_clip_edits_cannot_cross_owners_or_modify_publication_locked_media(tmp_path):
    store,uid,c,h,body,_=setup_edit(tmp_path)
    other=store.create_user('foreign-edit@example.com','long-password-for-test','Other')
    foreign=store.connect_worker(store.new_pairing(other))
    assert c.post('/api/worker/clip-edits/begin',json=body,headers={**h,'Authorization':'Bearer '+foreign}).status_code==409
    with store.connection() as db:
        db.execute("INSERT INTO publications(id,user_id,clip_id,platform,day,status,created,updated) VALUES('locked',?,?, 'tiktok','today','prepared',0,0)",(uid,body['jobId']))
    assert c.post('/api/worker/clip-edits/begin',json=body,headers=h).status_code==409
