import time
from concurrent.futures import ThreadPoolExecutor
import pytest
from server.store import Store
from server.publication import PublicationService,PublicationDenied,validate_upload_url
from server.oauth import OAuthService
from server.worker_jobs import WorkerJobs
from cryptography.fernet import Fernet

@pytest.fixture
def setup(tmp_path,monkeypatch):
    monkeypatch.setenv('CLIPBOT_TOKEN_ENCRYPTION_KEY',Fernet.generate_key().decode())
    store=Store(tmp_path/'publication.db');uid=store.create_user('publisher@example.com','a-good-long-password','Publisher')
    store.set_coverage(uid,review_daily=45,user_monthly=6000000,scouts=3,favorites=3,categories=3,posts=20)
    oauth=OAuthService(store,'https://clipbot.example');jobs=WorkerJobs(store);pub=PublicationService(store,oauth)
    return store,uid,oauth,jobs,pub

def test_upload_endpoints_fail_closed_before_tokens_leave_service():
    assert validate_upload_url('https://rupload.facebook.com/video-upload/v24.0/123','facebook','123')
    assert validate_upload_url('https://open-upload.tiktokapis.com/video/?upload_id=123','tiktok','123')
    for url in ['https://evil.test/a','https://rupload.facebook.com.evil.test/video-upload/v24.0/123','https://user:secret@rupload.facebook.com/a','file:///secret','http://rupload.facebook.com/a','https://rupload.facebook.com/video-upload/v24.0/999']:
        with pytest.raises(PublicationDenied):validate_upload_url(url,'facebook','123')

def test_beta_clip_reservations_atomic_and_crossposts_count_once(setup):
    store,uid,oauth,jobs,pub=setup
    for i in range(19):pub.reserve(uid,'clip'+str(i),'facebook')
    def reserve(i):
        try:return pub.reserve(uid,'new'+str(i),'facebook')
        except PublicationDenied:return None
    with ThreadPoolExecutor(max_workers=8) as pool:result=list(pool.map(reserve,range(8)))
    assert len([r for r in result if r])==1
    assert pub.reserve(uid,'clip0','instagram')
    with pytest.raises(PublicationDenied):pub.reserve(uid,'clip0','facebook')
    attempt=pub.snapshot(uid)[0]
    assert 'token' not in str(attempt).lower()

def test_prepare_requires_owned_ready_clip_and_encrypts_upload_grant(setup):
    store,uid,oauth,jobs,pub=setup
    job=jobs.enqueue(uid,{'platform':'twitch','login':'channel'})
    pub.artifact(uid,job,{'sha256':'a'*64,'sizeBytes':1000,'duration':20})
    with pytest.raises(PublicationDenied):pub.prepare(uid,job,'facebook',{'title':'Title','caption':'Caption','rightsAccepted':True})
    with store.connection() as db:db.execute("UPDATE pipeline_jobs SET stage='ready' WHERE id=?",(job,))
    oauth.vault.save(uid,'facebook',{'access_token':'OWNER-TOKEN','expires_at':time.time()+3600,'destinations':[{'id':'111','page_id':'111','name':'Page','access_token':'PAGE-SECRET'}]}, {'id':'owner','name':'Owner','destinationSelected':True,'destinationId':'111'})
    def request(method,url,**kwargs):return {'video_id':'123','upload_url':'https://rupload.facebook.com/video-upload/v24.0/123'}
    oauth.request=request
    attempt=pub.prepare(uid,job,'facebook',{'title':'Title','caption':'Caption','rightsAccepted':True})
    assert 'PAGE-SECRET' not in str(attempt)
    token=store.connect_worker(store.new_pairing(uid))
    grant=pub.grant(token,attempt['id'])
    assert grant['headers']['Authorization']=='OAuth PAGE-SECRET'
    with store.connection() as db:
        row=db.execute('SELECT * FROM publications WHERE id=?',(attempt['id'],)).fetchone()
        assert 'PAGE-SECRET' not in str(dict(row))
    other=store.create_user('other@example.com','a-good-long-password','Other');other_token=store.connect_worker(store.new_pairing(other))
    with pytest.raises(PublicationDenied):pub.grant(other_token,attempt['id'])
    with pytest.raises(PublicationDenied):pub.prepare(uid,job,'facebook',{'title':'Title','caption':'Caption','rightsAccepted':True})


def test_reconciliation_confirms_delivery_without_repeating_finish(setup):
    store,uid,oauth,jobs,pub=setup
    job=jobs.enqueue(uid,{'platform':'twitch','login':'channel'});pub.artifact(uid,job,{'sha256':'a'*64,'sizeBytes':1000,'duration':20})
    with store.connection() as db:db.execute("UPDATE pipeline_jobs SET stage='ready' WHERE id=?",(job,))
    oauth.vault.save(uid,'facebook',{'access_token':'OWNER','expires_at':time.time()+3600,'destinations':[{'id':'111','page_id':'111','name':'Page','access_token':'PAGE'}]}, {'id':'owner','name':'Owner','destinationSelected':True,'destinationId':'111'})
    finishes=[];published=False
    def request(method,url,**kwargs):
        if kwargs.get('data',{}).get('upload_phase')=='start':return {'video_id':'123','upload_url':'https://rupload.facebook.com/video-upload/v24.0/123'}
        if kwargs.get('data',{}).get('upload_phase')=='finish':finishes.append(1);return {'success':True}
        return {'status':{'publishing_phase':{'status':'complete' if published else 'not_started'},'uploading_phase':{'status':'complete'}}}
    oauth.request=request;attempt=pub.prepare(uid,job,'facebook',{'title':'Title','caption':'Caption','rightsAccepted':True})
    token=store.connect_worker(store.new_pairing(uid));pub.grant(token,attempt['id'])
    assert pub.uploaded(token,attempt['id'])['status']=='finishing'
    assert pub.reconcile(uid,attempt['id'])['status']=='finishing' and len(finishes)==1
    published=True
    assert pub.reconcile(uid,attempt['id'])['status']=='published'
    assert len(finishes)==1 and pub.snapshot(uid)[0]['receipt']['providerId']=='123'


def test_unlimited_plan_and_confirmed_failure_release_only_reserved_capacity(setup):
    store,uid,oauth,jobs,pub=setup
    with store.connection() as db:db.execute('INSERT INTO billing_state(user_id,subscription,customer,plan,status,expires) VALUES(?,?,?,?,?,?)',(uid,'subscription','customer','pro','active',time.time()+3600))
    for i in range(25):pub.reserve(uid,'unlimited'+str(i),'facebook')
    rows=pub.snapshot(uid)
    with store.connection() as db:row=db.execute('SELECT * FROM publications WHERE id=?',(rows[0]['id'],)).fetchone()
    pub.failed(uid,row)
    with store.connection() as db:assert db.execute('SELECT COUNT(*) FROM clip_capacity WHERE user_id=?',(uid,)).fetchone()[0]==24


def test_upload_grant_api_never_accepts_browser_session_as_device(setup):
    from fastapi.testclient import TestClient
    from server.app import create_app
    store,uid,oauth,jobs,pub=setup;raw,_=store.new_session(uid)
    app=create_app(store,origin='http://testserver',oauth=oauth)
    with TestClient(app) as client:
        client.cookies.set('clipbot_session',raw);csrf=client.get('/api/account').json()['csrfToken']
        headers={'Origin':'http://testserver','X-CSRF-Token':csrf}
        assert client.post('/api/worker/upload-grant',json={'attemptId':'a'*32},headers=headers).status_code==401
        assert client.get('/api/pipeline/publications').json()=={'publications':[]}
        assert client.get('/api/worker/state').status_code==401
        token=store.connect_worker(store.new_pairing(uid))
        assert client.get('/api/worker/state',headers={'Authorization':'Bearer '+token}).status_code==200


def test_expired_poll_cannot_finish_or_release_new_poll_lease(setup):
    store,uid,oauth,jobs,pub=setup
    job=jobs.enqueue(uid,{'platform':'twitch','login':'channel'})
    pub.artifact(uid,job,{'sha256':'a'*64,'sizeBytes':1000,'duration':20})
    with store.connection() as db:db.execute("UPDATE pipeline_jobs SET stage='ready' WHERE id=?",(job,))
    oauth.vault.save(uid,'facebook',{'access_token':'OWNER','expires_at':time.time()+3600,'destinations':[{'id':'111','page_id':'111','name':'Page','access_token':'PAGE'}]}, {'id':'owner','name':'Owner','destinationSelected':True,'destinationId':'111'})
    finishes=[];polls=[];attempt=None
    def request(method,url,**kwargs):
        if kwargs.get('data',{}).get('upload_phase')=='start':return {'video_id':'123','upload_url':'https://rupload.facebook.com/video-upload/v24.0/123'}
        if kwargs.get('data',{}).get('upload_phase')=='finish':finishes.append(1);return {'success':True}
        polls.append(1)
        if len(polls)==1:
            with store.connection() as db:db.execute('UPDATE publications SET lease_expires=0 WHERE id=?',(attempt['id'],))
            pub.reconcile(uid,attempt['id'])
        return {'status':{'uploading_phase':{'status':'complete'}}}
    oauth.request=request
    attempt=pub.prepare(uid,job,'facebook',{'title':'Title','caption':'Caption','rightsAccepted':True})
    token=store.connect_worker(store.new_pairing(uid));pub.grant(token,attempt['id'])
    pub.reconcile(uid,attempt['id'])
    assert len(finishes)==1
