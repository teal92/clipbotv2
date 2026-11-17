from types import SimpleNamespace as NS
import pytest
from fastapi.testclient import TestClient
from server.app import create_app
from server.store import Store
from server.billing import Billing
from server.billing_modes import bind_mode
from server.legal import POLICY_VERSION
from test_billing import Provider,event
from test_analysis import Messages,transcript

def customer(tmp_path,monkeypatch):
 store=Store(tmp_path/'customer.db');uid=store.create_user('customer@example.test','SafePassword!2026','customer')
 provider=Provider();billing=Billing(store,'http://testserver',provider,{p:'price_'+p for p in ('starter','creator','pro')})
 billing.start(uid,'starter');billing.receive(event());store.save_preferences(uid,{'usagePreset':'balanced'})
 billing.mode='live';billing.live=True;store.billing_mode='live'
 with store.connection() as db:bind_mode(db,'state',uid,'live')
 monkeypatch.setenv('CLIPBOT_CUSTOMER_ANALYSIS_ENABLED','1');monkeypatch.setenv('CLIPBOT_ENFORCE_CUSTOMER_ACCESS','1')
 app=create_app(store,origin='http://testserver',billing=billing);messages=Messages();app.state.analysis.client=NS(messages=messages)
 with store.connection() as db:db.execute('INSERT INTO email_verification VALUES(?,?)',(uid,1));db.execute('INSERT INTO legal_acceptances VALUES(?,?,?)',(uid,POLICY_VERSION,1))
 from server.scouts import ScoutStore
 ScoutStore(store).save(uid,{'running':True,'slots':1,'forced':[],'favorites':[],'categories':[]})
 token=store.connect_worker(store.new_pairing(uid));jobs=app.state.pipeline_jobs
 job=jobs.enqueue(uid,{'platform':'twitch','login':'channel'});claim=jobs.claim(token)
 # Paid capture admission requires monitoring; initialize it explicitly.
 return store,uid,app,messages,token,jobs,job,claim

def ready_customer(tmp_path,monkeypatch):
 result=customer(tmp_path,monkeypatch);store,uid,app,messages,token,jobs,job,claim=result
 jobs.report(token,job,claim['lease'],{'stage':'capturing'});jobs.report(token,job,claim['lease'],{'stage':'transcribing'})
 body={'jobId':job,'lease':claim['lease'],'duration':120,'transcript':transcript()};headers={'Origin':'http://testserver','Authorization':'Bearer '+token}
 return result,body,headers

def test_verified_paid_customer_can_analyze_without_owner_test_or_beta_acceptance(tmp_path,monkeypatch):
 (store,uid,app,messages,*_),body,headers=ready_customer(tmp_path,monkeypatch)
 with TestClient(app) as client:response=client.post('/api/worker/analyze',headers=headers,json=body)
 assert response.status_code==200 and response.json()['candidate']['id']==body['jobId']
 assert messages.calls==1

@pytest.mark.parametrize('change',['switch_off','wrong_billing_mode','unverified_email','old_policy'])
def test_customer_analysis_rechecks_release_payment_and_identity_before_provider(tmp_path,monkeypatch,change):
 (store,uid,app,messages,*_),body,headers=ready_customer(tmp_path,monkeypatch)
 if change=='switch_off':monkeypatch.delenv('CLIPBOT_CUSTOMER_ANALYSIS_ENABLED')
 elif change=='wrong_billing_mode':
  with store.connection() as db:bind_mode(db,'state',uid,'test')
 else:
  with store.connection() as db:db.execute('DELETE FROM '+('email_verification' if change=='unverified_email' else 'legal_acceptances')+' WHERE user_id=?',(uid,))
 with TestClient(app) as client:response=client.post('/api/worker/analyze',headers=headers,json=body)
 assert response.status_code in (409,428)
 assert messages.calls==0

@pytest.mark.parametrize('change',['switch_off','wrong_billing_mode','unverified_email','old_policy','lease_revoked'])
def test_customer_access_revoked_during_token_count_never_dispatches(tmp_path,monkeypatch,change):
 (store,uid,app,messages,*_),body,headers=ready_customer(tmp_path,monkeypatch)
 def count(**kwargs):
  if change=='switch_off':monkeypatch.delenv('CLIPBOT_CUSTOMER_ANALYSIS_ENABLED')
  else:
   with store.connection() as db:
    if change=='wrong_billing_mode':bind_mode(db,'state',uid,'test')
    elif change=='lease_revoked':db.execute("UPDATE pipeline_jobs SET lease_expires=0 WHERE id=?",(body['jobId'],))
    else:db.execute('DELETE FROM '+('email_verification' if change=='unverified_email' else 'legal_acceptances')+' WHERE user_id=?',(uid,))
  return NS(input_tokens=100)
 messages.count_tokens=count
 with TestClient(app) as client:response=client.post('/api/worker/analyze',headers=headers,json=body)
 assert response.status_code==409 and messages.calls==0
 assert app.state.ledger.snapshot(uid)['reservedMicros']==0


def test_customer_readiness_required_even_when_optional_gate_is_disabled(tmp_path,monkeypatch):
 (store,uid,app,messages,*_),body,headers=ready_customer(tmp_path,monkeypatch)
 monkeypatch.setenv('CLIPBOT_ENFORCE_CUSTOMER_ACCESS','0')
 with store.connection() as db:db.execute('DELETE FROM email_verification WHERE user_id=?',(uid,))
 with TestClient(app) as client:response=client.post('/api/worker/analyze',headers=headers,json=body)
 assert response.status_code==409 and messages.calls==0


@pytest.mark.parametrize('change',[None,'switch_off','wrong_billing_mode','unverified_email','old_policy'])
def test_worker_configuration_uses_same_protected_customer_gate(tmp_path,monkeypatch,change):
 store,uid,app,messages,token,*_=customer(tmp_path,monkeypatch)
 if change=='switch_off':monkeypatch.delenv('CLIPBOT_CUSTOMER_ANALYSIS_ENABLED')
 elif change=='wrong_billing_mode':
  with store.connection() as db:bind_mode(db,'state',uid,'test')
 elif change:
  with store.connection() as db:db.execute('DELETE FROM '+('email_verification' if change=='unverified_email' else 'legal_acceptances')+' WHERE user_id=?',(uid,))
 with TestClient(app) as client:
  response=client.get('/api/worker/config',headers={'Authorization':'Bearer '+token})
 assert response.status_code==200
 assert response.json()['analysisEnabled'] is (change is None)
 assert response.json()['customerAnalysisEnabled'] is (change is None)
 assert response.json()['betaAccepted'] is False
 assert messages.calls==0


@pytest.mark.parametrize('authorized,enabled,expected',[(True,True,None),(False,True,'beta_required'),(True,False,'analysis_paused')])
def test_worker_runtime_requires_legacy_beta_only_for_owner_test_path(tmp_path,authorized,enabled,expected):
 import threading,time
 from concurrent.futures import Future
 from worker.runtime import MonitorRuntime
 class Client:
  report=None
  def configuration(self):return {'effective':{'running':True,'slots':1,'forced':[],'favorites':[],'categories':[]},'analysisEnabled':enabled,'betaAccepted':False,'customerAnalysisEnabled':authorized}
  def companion_heartbeat(self,data):self.report=data
 class Pool:
  def submit(self,*args):return Future()
  def shutdown(self,**kwargs):pass
 client=Client();runtime=MonitorRuntime(client,tmp_path,lambda *args:None,capture_function=lambda *args:None)
 runtime.pool.shutdown(wait=True);runtime.pool=Pool();runtime.last_discovery=time.monotonic()
 runtime.sources=[{'platform':'twitch','login':'channel','live':True,'viewers':10}]
 try:
  runtime.tick()
  assert bool(runtime.active) is (expected is None)
  assert client.report['errorCode']==expected
 finally:runtime.close()
