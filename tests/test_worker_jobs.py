import time
from concurrent.futures import ThreadPoolExecutor
import pytest
from server.store import Store
from server.worker_jobs import WorkerJobs, WorkerDenied

@pytest.fixture
def setup(tmp_path):
    store=Store(tmp_path/'jobs.db'); uid=store.create_user('worker@example.com','a-good-long-password','Worker')
    token=store.connect_worker(store.new_pairing(uid)); jobs=WorkerJobs(store)
    return store,uid,token,jobs

def test_job_leases_are_atomic_and_revoked_devices_cannot_report(setup):
    store,uid,token,jobs=setup
    job=jobs.enqueue(uid,{'platform':'twitch','login':'streamer'})
    with ThreadPoolExecutor(max_workers=5) as pool:claims=list(pool.map(lambda _:jobs.claim(token),range(5)))
    claim=next(c for c in claims if c)
    assert len([c for c in claims if c])==1
    assert claim['id']==job and 'user_id' not in claim
    with pytest.raises(WorkerDenied):jobs.report(token,job,'wrong',{'stage':'capturing'})
    jobs.report(token,job,claim['lease'],{'stage':'capturing'})
    with pytest.raises(WorkerDenied):jobs.report(token,job,claim['lease'],{'stage':'published'})
    other=store.create_user('other@example.com','a-good-long-password','Other');other_token=store.connect_worker(store.new_pairing(other))
    assert jobs.claim(other_token) is None and jobs.snapshot(other)==[]
    with pytest.raises(WorkerDenied):jobs.report(other_token,job,claim['lease'],{'stage':'transcribing'})
    store.revoke_workers(uid)
    with pytest.raises(WorkerDenied):jobs.report(token,job,claim['lease'],{'stage':'transcribing'})

def test_stale_lease_cancel_and_metrics_validation(setup):
    store,uid,token,jobs=setup; job=jobs.enqueue(uid,{'platform':'kick','login':'streamer'})
    claim=jobs.claim(token)
    with jobs.store.connection() as db:db.execute('UPDATE pipeline_jobs SET lease_expires=0 WHERE id=?',(job,))
    with pytest.raises(WorkerDenied):jobs.report(token,job,claim['lease'],{'stage':'capturing'})
    replacement=jobs.claim(token)
    assert replacement['lease']!=claim['lease']
    for metrics in [{'cpuPercent':float('nan')},{'cpuPercent':999},{'password':'SECRET'}]:
        with pytest.raises(WorkerDenied):jobs.report(token,job,replacement['lease'],{'stage':'capturing','metrics':metrics})
    assert jobs.cancel('other',job) is False
    assert jobs.cancel(uid,job)
    with pytest.raises(WorkerDenied):jobs.report(token,job,replacement['lease'],{'stage':'capturing'})
    assert jobs.snapshot(uid)[0]['stage']=='cancelled'


def test_api_uses_session_or_device_identity_and_existing_csrf(setup):
    from fastapi.testclient import TestClient
    from server.app import create_app
    store,uid,token,jobs=setup
    store.set_coverage(uid,review_daily=45,user_monthly=6000000,scouts=3,favorites=2,categories=1,posts=20)
    raw,csrf=store.new_session(uid)
    app=create_app(store,origin='http://testserver')
    with TestClient(app) as client:
        client.cookies.set('clipbot_session',raw)
        assert client.get('/api/scouts').status_code==200
        config={'running':False,'slots':2,'forced':[],'favorites':[],'categories':[]}
        assert client.put('/api/scouts',json=config,headers={'Origin':'http://testserver'}).status_code==403
        csrf=client.get('/api/account').json()['csrfToken']
        assert client.put('/api/scouts',json=config,headers={'Origin':'http://testserver','X-CSRF-Token':csrf}).status_code==200
        assert client.put('/api/scouts',json={**config,'running':True},headers={'Origin':'http://testserver','X-CSRF-Token':csrf}).status_code==409
        client.cookies.clear()
        assert client.get('/api/scouts').status_code==401
        assert client.get('/api/worker/config').status_code==401
        headers={'Origin':'http://testserver','Authorization':'Bearer '+token}
        assert client.get('/api/worker/config',headers=headers).json()['effective']['slots']==2
        jobs.enqueue(uid,{'platform':'twitch','login':'streamer'})
        lease=client.post('/api/worker/jobs/claim',headers=headers).json()['job']
        assert lease['source']['login']=='streamer'
        assert client.post('/api/worker/jobs/report',json={'jobId':lease['id'],'lease':lease['lease'],'event':{'stage':'capturing'}},headers=headers).status_code==200
        store.revoke_workers(uid)
        assert client.get('/api/worker/config',headers=headers).status_code==401


def test_worker_open_enforces_paid_running_slots_and_deduplicates_source(setup):
    from server.scouts import ScoutStore
    store,uid,token,jobs=setup
    store.set_coverage(uid,review_daily=45,user_monthly=6000000,scouts=2,favorites=0,categories=0,posts=20)
    scouts=ScoutStore(store);scouts.save(uid,{'running':True,'slots':1,'forced':[],'favorites':[],'categories':[]})
    first=jobs.open(token,{'platform':'twitch','login':'streamer'})
    with pytest.raises(WorkerDenied):jobs.open(token,{'platform':'twitch','login':'streamer'})
    with pytest.raises(WorkerDenied):jobs.open(token,{'platform':'kick','login':'different'})
    jobs.cancel(uid,first['id'])
    assert jobs.open(token,{'platform':'kick','login':'different'})['lease']
    scouts.save(uid,{'running':False,'slots':1,'forced':[],'favorites':[],'categories':[]})
    with pytest.raises(WorkerDenied):jobs.open(token,{'platform':'twitch','login':'another'})


def test_expired_capture_frees_slots_without_reusing_old_lease(setup):
    from server.scouts import ScoutStore
    store,uid,token,jobs=setup
    store.set_coverage(uid,review_daily=45,user_monthly=6000000,scouts=1,favorites=0,categories=0,posts=20)
    ScoutStore(store).save(uid,{'running':True,'slots':1,'forced':[],'favorites':[],'categories':[]})
    first=jobs.open(token,{'platform':'twitch','login':'one'})
    jobs.report(token,first['id'],first['lease'],{'stage':'capturing'})
    with store.connection() as db:db.execute('UPDATE pipeline_jobs SET lease_expires=0 WHERE id=?',(first['id'],))
    assert jobs.open(token,{'platform':'twitch','login':'two'})['id']!=first['id']
    with pytest.raises(WorkerDenied):jobs.report(token,first['id'],first['lease'],{'stage':'transcribing'})


def test_restart_can_resume_owned_review_with_fresh_lease_only(setup):
    store,uid,token,jobs=setup
    job=jobs.enqueue(uid,{'platform':'twitch','login':'one'});claim=jobs.claim(token)
    with store.connection() as db:db.execute("UPDATE pipeline_jobs SET stage='review',lease_expires=0 WHERE id=?",(job,))
    other=store.create_user('restart-other@example.com','a-good-long-password','Other');other_token=store.connect_worker(store.new_pairing(other))
    with pytest.raises(WorkerDenied):jobs.resume(other_token,job)
    resumed=jobs.resume(token,job)
    assert resumed['lease']!=claim['lease'] and resumed['stage']=='review'
    with pytest.raises(WorkerDenied):jobs.resume(token,job)
    jobs.report(token,job,resumed['lease'],{'stage':'review'})

def test_preference_save_cannot_restart_after_concurrent_stop(setup):
 from fastapi.testclient import TestClient
 from server.app import create_app
 from server.scouts import ScoutStore
 store,uid,token,jobs=setup;store.set_coverage(uid,review_daily=45,user_monthly=6000000,scouts=3,favorites=2,categories=1,posts=20)
 app=create_app(store,origin='http://testserver');scouts=app.state.scouts;cfg={'running':True,'slots':2,'forced':[],'favorites':[],'categories':[]};scouts.save(uid,cfg)
 original=scouts.save
 def interleaved(account,selection,**kwargs):
  original(account,{**selection,'running':False})
  return original(account,selection,**kwargs)
 scouts.save=interleaved;raw,_=store.new_session(uid)
 with TestClient(app) as client:
  client.cookies.set('clipbot_session',raw);csrf=client.get('/api/account').json()['csrfToken']
  response=client.put('/api/scouts',json=cfg,headers={'Origin':'http://testserver','X-CSRF-Token':csrf})
 assert response.status_code==409 and scouts.snapshot(uid)['configuration']['running'] is False

@pytest.mark.parametrize('code',['dependency_mismatch','transcription_unavailable','queue_full','no_speech'])
def test_safe_failure_reason_is_retained_for_account_logs(setup,code):
    store,uid,token,jobs=setup
    job=jobs.enqueue(uid,{'platform':'twitch','login':'streamer'})
    claim=jobs.claim(token)
    jobs.report(token,job,claim['lease'],{'stage':'capturing'})
    jobs.report(token,job,claim['lease'],{'stage':'failed','errorCode':code})
    assert jobs.snapshot(uid)[0]['errorCode']==code
    assert jobs.snapshot('another-account')==[]
