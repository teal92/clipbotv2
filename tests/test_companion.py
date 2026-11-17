import time
import pytest
from server.store import Store
from server.scouts import ScoutStore
from server.companion import CompanionStore

@pytest.fixture
def setup(tmp_path):
 store=Store(tmp_path/'companion.db');uid=store.create_user('control@example.com','a-good-long-password','Control')
 store.set_coverage(uid,review_daily=45,user_monthly=6000000,scouts=6,favorites=3,categories=3,posts=20)
 token=store.connect_worker(store.new_pairing(uid));scouts=ScoutStore(store);companion=CompanionStore(store)
 return store,uid,token,scouts,companion

def report(revision='',monitoring=False):return {'ready':True,'monitoring':monitoring,'acknowledgedRevision':revision,'hardwareSlots':2,'activeScouts':0,'errorCode':None}

def test_trigger_configuration_failure_is_reported_and_blocks_start(setup):
 store,uid,token,scouts,c=setup
 c.report(token,{**report(),'errorCode':'trigger_settings_unavailable'})
 assert c.status(uid)['errorCode']=='trigger_settings_unavailable'
 assert c.status(uid)['state']=='attention'
 with pytest.raises(ValueError):c.control(uid,True)

def test_control_requires_ready_device_and_preserves_preferences(setup):
 store,uid,token,scouts,c=setup
 with pytest.raises(ValueError):c.control(uid,True)
 c.report(token,report());assert c.status(uid)['state']=='ready'
 saved=scouts.save(uid,{'running':False,'slots':2,'forced':[{'platform':'twitch','login':'one'}],'favorites':[],'categories':[]});c.report(token,report(saved['revision']))
 started=c.control(uid,True);assert started['state']=='starting'
 assert scouts.snapshot(uid)['configuration']['forced']==[{'platform':'twitch','login':'one'}]
 c.report(token,report(started['revision'],True));assert c.status(uid)['state']=='running'
 stopped=c.control(uid,False);assert stopped['state']=='stopping'
 c.report(token,report(started['revision'],True));assert c.status(uid)['state']=='stopping'
 c.report(token,report(stopped['revision'],False));assert c.status(uid)['state']=='ready'

def test_offline_stop_default_slots_and_revocation(setup):
 store,uid,token,scouts,c=setup
 c.report(token,report());started=c.control(uid,True)
 assert scouts.snapshot(uid)['configuration']['slots']==2
 store.revoke_workers(uid);assert c.status(uid)['state']=='offline'
 assert c.control(uid,False)['requestedRunning'] is False
 with pytest.raises(ValueError):c.report(token,report())

def test_stale_ack_and_download_fail_closed(setup,monkeypatch):
 store,uid,token,scouts,c=setup;c.report(token,report())
 with store.connection() as db:db.execute('UPDATE companion_state SET last_seen=0')
 assert c.status(uid)['state']=='offline'
 monkeypatch.setenv('CLIPBOT_COMPANION_DOWNLOAD_URL','https://user:secret@evil.test/setup.exe')
 assert c.status(uid)['download']['available'] is False
import pytest
from fastapi.testclient import TestClient
from server.app import create_app

def test_control_api_requires_session_csrf_and_owns_state(setup):
 store,uid,token,scouts,c=setup;app=create_app(store,origin='http://testserver')
 with TestClient(app) as client:
  assert client.post('/api/companion/control',json={'running':False},headers={'Origin':'http://testserver'}).status_code==401
  raw,_=store.new_session(uid);client.cookies.set('clipbot_session',raw)
  assert client.post('/api/companion/control',json={'running':False},headers={'Origin':'http://testserver'}).status_code==403
  csrf=client.get('/api/account').json()['csrfToken'];headers={'Origin':'http://testserver','X-CSRF-Token':csrf}
  assert client.post('/api/companion/control',json={'running':False,'userId':'other'},headers=headers).status_code==422
  assert client.post('/api/companion/control',json={'running':False},headers=headers).status_code==200
  assert client.get('/api/companion/status').json()['state']=='offline'
  assert client.post('/api/worker/companion-heartbeat',json=report(),headers={'Origin':'http://testserver'}).status_code==401
  assert client.post('/api/worker/companion-heartbeat',json=report(),headers={'Authorization':'Bearer '+token,'Origin':'http://testserver'}).status_code==200

def test_stale_idle_report_cannot_acknowledge_stop(setup):
 store,uid,token,scouts,c=setup
 c.report(token,report());c.control(uid,True)
 stopped=c.control(uid,False)
 assert stopped['state']=='stopping'
 c.report(token,report(stopped['revision'],False))
 assert c.status(uid)['state']=='ready'

def test_missing_tools_health_retries_and_preserves_attention(setup):
 from worker.lifecycle import CompanionHealth
 from unittest.mock import Mock
 store,uid,token,scouts,c=setup;client=Mock();client.token=token
 client.companion_heartbeat.side_effect=[TimeoutError(),lambda data:c.report(token,data)]
 health=CompanionHealth(client,2)
 assert health.tick()==5
 client.companion_heartbeat.side_effect=lambda data:c.report(token,data)
 assert health.tick()==5 and c.status(uid)['state']=='attention'
 with store.connection() as db:db.execute('UPDATE companion_state SET last_seen=0')
 assert c.status(uid)['state']=='offline'
 health.tick();assert c.status(uid)['state']=='attention'

def test_start_requires_supported_companion_version_at_service_boundary(setup):
 store,uid,token,scouts,c=setup;c.required_version='0.2.1-beta';c.report(token,report())
 with pytest.raises(ValueError,match='Update the companion'):c.control(uid,True)
 c.report(token,{**report(),'version':'0.2.1-beta'})
 assert c.control(uid,True)['requestedRunning']
