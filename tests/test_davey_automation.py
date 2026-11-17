import importlib.util,json,time
import pytest
from fastapi.testclient import TestClient
from cryptography.fernet import Fernet
from test_customer_analysis_release import ready_customer
from test_davey_progression import decisions,policy,validation


def automatic_customer(tmp_path,monkeypatch):
    monkeypatch.setenv('CLIPBOT_TOKEN_ENCRYPTION_KEY',Fernet.generate_key().decode())
    (store,uid,app,_,token,jobs,job,claim),body,headers=ready_customer(tmp_path,monkeypatch)
    pub=app.state.publication;oauth=app.state.oauth;calls=[];finished=False
    oauth.vault.save(uid,'facebook',{'access_token':'OWNER','expires_at':time.time()+3600,'destinations':[{'id':'111','access_token':'PAGE'}]},{'id':'owner','name':'Selected Page','destinationSelected':True,'destinationId':'111'})
    def request(method,url,**kwargs):
        nonlocal finished
        calls.append((method,url))
        if method=='GET':return {'status':{'publishing_phase':{'status':'complete' if finished else 'not_started'},'uploading_phase':{'status':'complete'}}}
        if kwargs.get('data',{}).get('upload_phase')=='finish':finished=True;return {'success':True}
        return {'video_id':'123','upload_url':'https://rupload.facebook.com/video-upload/v24.0/123'}
    oauth.request=request
    davey=store.davey;decisions(store,uid,100)
    davey.save(uid,policy(davey,uid,personalContext=True,shadowEnabled=True,sources=[{'platform':'twitch','login':'channel'}]))
    validation(store,uid,davey)
    monkeypatch.setenv('CLIPBOT_AUTONOMY_ENABLED','1')
    davey.save(uid,policy(davey,uid,automatic=True,rightsAccepted=True,platforms=['facebook'],dailyPostLimit=1))
    candidate={'id':job,'score':96,'title':'A moment','caption':'Caption','rationale':'Evidence','start':0,'end':20,'safetyFlags':[]}
    artifact={'sha256':'a'*64,'sizeBytes':100,'duration':20,'width':1080,'height':1920,'framing':'blurred_fit','previewToken':'b'*64}
    with store.connection() as db:
        db.execute('INSERT INTO candidates VALUES(?,?,?)',(job,uid,json.dumps(candidate)))
        db.execute("UPDATE pipeline_jobs SET stage='review' WHERE id=?",(job,))
        db.execute('INSERT INTO clip_artifacts VALUES(?,?,?)',(uid,job,json.dumps(artifact)))
    davey.prediction(uid,job,candidate,davey.context_key(uid))
    return store,uid,app,token,job,headers,calls


def test_automatic_dispatch_uses_existing_broker_and_never_teaches_itself(tmp_path,monkeypatch):
    assert importlib.util.find_spec('server.davey_automation') is not None
    store,uid,app,token,job,headers,calls=automatic_customer(tmp_path,monkeypatch)
    with TestClient(app) as client:
        before=store.davey.status(uid)
        response=client.post('/api/worker/davey-dispatch',json={},headers=headers)
        assert response.status_code==200 and response.json()['prepared']==1
        attempts=app.state.publication.snapshot(uid);assert len(attempts)==1
        assert client.post('/api/worker/davey-dispatch',json={},headers=headers).json()['prepared']==0
        grant=app.state.publication.grant(token,attempts[0]['id']);assert grant['artifact']['sha256']=='a'*64
        app.state.publication.uploaded(token,attempts[0]['id'])
        app.state.publication.reconcile(uid,attempts[0]['id'])
        assert app.state.publication.snapshot(uid)[0]['status']=='published'
        assert any(url.endswith('/video_reels') for method,url in calls if method=='POST')
        after=store.davey.status(uid)
        assert before['manualDecisions']==after['manualDecisions'] and before['validation']==after['validation']
        with store.connection() as db:
            review=json.loads(db.execute('SELECT data FROM reviews WHERE candidate_id=?',(job,)).fetchone()[0])
            assert review['actor']=='davey'


@pytest.mark.parametrize('change',['release','consent','stop','email','policy','plan','source','flags','edit','lease','human_reject'])
def test_automatic_dispatch_fails_closed_before_provider(tmp_path,monkeypatch,change):
    assert importlib.util.find_spec('server.davey_automation') is not None
    store,uid,app,token,job,headers,calls=automatic_customer(tmp_path,monkeypatch)
    if change=='release':monkeypatch.delenv('CLIPBOT_AUTONOMY_ENABLED')
    elif change=='consent':store.davey.save(uid,policy(store.davey,uid,personalContext=False))
    elif change=='human_reject':store.save_review(uid,job,'reject',[],'',local_learning=True)
    else:
        with store.connection() as db:
            if change=='stop':db.execute('UPDATE debug_sessions SET stopped=? WHERE user_id=?',(time.time(),uid))
            elif change=='email':db.execute('DELETE FROM email_verification WHERE user_id=?',(uid,))
            elif change=='policy':db.execute('DELETE FROM legal_acceptances WHERE user_id=?',(uid,))
            elif change=='plan':db.execute("UPDATE billing_state SET status='cancelled' WHERE user_id=?",(uid,))
            elif change=='lease':db.execute('UPDATE pipeline_jobs SET lease_expires=0 WHERE id=?',(job,))
            elif change=='source':db.execute('UPDATE pipeline_jobs SET source=? WHERE id=?',(json.dumps({'platform':'kick','login':'other'}),job))
            else:
                candidate=json.loads(db.execute('SELECT data FROM candidates WHERE id=?',(job,)).fetchone()[0]);candidate.update({'safetyFlags':['private_information']} if change=='flags' else {'title':'Edited'})
                db.execute('UPDATE candidates SET data=? WHERE id=?',(json.dumps(candidate),job))
    with TestClient(app) as client:
        response=client.post('/api/worker/davey-dispatch',json={},headers=headers)
        assert response.status_code in (200,409) and response.json().get('prepared',0)==0
    assert calls==[]


@pytest.mark.parametrize('boundary',['grant','finish'])
@pytest.mark.parametrize('change',['stop','consent','destination','plan'])
def test_prepared_automatic_attempt_is_revocable_at_each_mutation_boundary(tmp_path,monkeypatch,boundary,change):
    assert importlib.util.find_spec('server.davey_automation') is not None
    from server.publication import PublicationDenied
    store,uid,app,token,job,headers,calls=automatic_customer(tmp_path,monkeypatch)
    with TestClient(app) as client:assert client.post('/api/worker/davey-dispatch',json={},headers=headers).json()['prepared']==1
    pub=app.state.publication;attempt=pub.snapshot(uid)[0]['id']
    if boundary=='finish':pub.grant(token,attempt)
    if change=='consent':store.davey.save(uid,policy(store.davey,uid,personalContext=False))
    elif change=='destination':app.state.oauth.vault.save(uid,'facebook',{'access_token':'OTHER','expires_at':time.time()+3600,'destinations':[{'id':'222','access_token':'NEW'}]},{'id':'owner','name':'Selected Page','destinationSelected':True,'destinationId':'222'})
    else:
        with store.connection() as db:
            if change=='stop':db.execute('UPDATE debug_sessions SET stopped=? WHERE user_id=?',(time.time(),uid))
            else:db.execute("UPDATE billing_state SET status='cancelled' WHERE user_id=?",(uid,))
    mutations=len([1 for method,_ in calls if method=='POST'])
    with pytest.raises(PublicationDenied):
        if boundary=='grant':pub.grant(token,attempt)
        else:pub.uploaded(token,attempt)
    assert len([1 for method,_ in calls if method=='POST'])==mutations


def test_concurrent_dispatch_and_daily_cap_reserve_once(tmp_path,monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    store,uid,app,token,job,headers,calls=automatic_customer(tmp_path,monkeypatch)
    pub=app.state.publication
    with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(lambda _:pub.automation.dispatch(uid,token),range(2)))
    assert sum(result['prepared'] for result in results)==1
    assert len(calls)==1
    second=app.state.pipeline_jobs.enqueue(uid,{'platform':'twitch','login':'channel'})
    with store.connection() as db:
        old=db.execute('SELECT * FROM pipeline_jobs WHERE id=?',(job,)).fetchone()
        candidate=json.loads(db.execute('SELECT data FROM candidates WHERE id=?',(job,)).fetchone()[0]);candidate['id']=second
        artifact=db.execute('SELECT data FROM clip_artifacts WHERE clip_id=?',(job,)).fetchone()[0]
        db.execute("UPDATE pipeline_jobs SET stage='review',device=?,lease=?,lease_expires=? WHERE id=?",(old['device'],old['lease'],old['lease_expires'],second))
        db.execute('INSERT INTO candidates VALUES(?,?,?)',(second,uid,json.dumps(candidate)))
        db.execute('INSERT INTO clip_artifacts VALUES(?,?,?)',(uid,second,artifact))
    store.davey.prediction(uid,second,candidate,store.davey.context_key(uid))
    assert pub.automation.dispatch(uid,token)['prepared']==0 and len(calls)==1


def test_new_monitoring_session_cannot_reauthorize_old_clip(tmp_path,monkeypatch):
    store,uid,app,token,job,headers,calls=automatic_customer(tmp_path,monkeypatch)
    from server.debug_sessions import DebugSessions
    with store.connection(atomic=True) as db:
        DebugSessions.transition_in(db,uid,True,False,{})
        DebugSessions.transition_in(db,uid,False,True,{})
    assert app.state.publication.automation.dispatch(uid,token)['prepared']==0
    assert calls==[]

