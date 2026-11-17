from fastapi.testclient import TestClient
from server.app import create_app
from server.store import Store
from server.pipeline_events import EventStore

def test_logs_are_account_owned_and_worker_diagnostics_reject_secrets(tmp_path):
    store=Store(tmp_path/'logs.db');uid=store.create_user('logs@example.com','long-password-test','Logs');other=store.create_user('foreignlogs@example.com','long-password-test','Other')
    app=create_app(store,origin='http://testserver');events=EventStore(store)
    events.record(uid,'analysis_dispatch',job_id='a'*32,source='davey');events.record(other,'analysis_dispatch',job_id='b'*32,source='davey')
    token=store.connect_worker(store.new_pairing(uid));job=app.state.pipeline_jobs.enqueue(uid,{'platform':'kick','login':'one'});claim=app.state.pipeline_jobs.claim(token)
    with TestClient(app) as c:
        assert c.get('/api/logs').status_code==401
        raw,_=store.new_session(uid);c.cookies.set('clipbot_session',raw)
        result=c.get('/api/logs').json();assert result['events'] and all('b'*32 not in e['message'] for e in result['events'])
        assert c.get('/api/logs?after='+str(result['cursor'])).json()['events']==[]
        headers={'Origin':'http://testserver','Authorization':'Bearer '+token};body={'jobId':job,'lease':claim['lease'],'event':'transcription_started','source':'transcription','stage':'transcribing'}
        assert c.post('/api/worker/diagnostic',json={**body,'transcript':'PRIVATE'},headers=headers).status_code==422
        assert c.post('/api/worker/diagnostic',json=body,headers=headers).status_code==200
        assert c.get('/api/logs').json()['events'][-1]['source']=='transcription'
