import json,pytest
from server.store import Store
from server.pipeline_events import EventStore
from server.debug_sessions import DebugSessions

def test_session_retains_full_bounded_history_and_owner_isolation(tmp_path):
 store=Store(tmp_path/'session.db');sessions=DebugSessions(store);events=EventStore(store)
 config={'running':True,'slots':2,'platformSlots':{'twitch':1,'kick':1},'forced':[{'platform':'kick','login':'spreen'}]}
 sid=sessions.transition('owner',False,True,config)
 assert sessions.transition('owner',True,True,config)==sid
 for n in range(510):events.record('owner','job_reported',job_id=str(n),stage='capturing')
 sessions.transition('owner',True,False,{**config,'running':False})
 bundle=sessions.bundle('owner',sid)
 assert bundle['session']['state']=='stopped'
 assert len(bundle['events'])==510
 assert bundle['session']['configuration']['forced']==config['forced']
 with pytest.raises(KeyError):sessions.bundle('other',sid)
 events.record('owner','job_cancelled',job_id='after',stage='cancelled')
 assert len(sessions.bundle('owner',sid)['events'])==510
 assert 'private' not in json.dumps(bundle)


def test_session_download_requires_owner_and_has_attachment(tmp_path):
 from fastapi.testclient import TestClient
 from server.app import create_app
 store=Store(tmp_path/'api.db');uid=store.create_user('bundle@example.com','long-password-test','Bundle');other=store.create_user('otherbundle@example.com','long-password-test','Other')
 app=create_app(store,origin='http://testserver');sid=DebugSessions(store).transition(uid,False,True,{'slots':2,'forced':[]})
 with TestClient(app) as c:
  assert c.get('/api/logs/sessions').status_code==401
  raw,_=store.new_session(other);c.cookies.set('clipbot_session',raw)
  assert c.get('/api/logs/sessions/'+sid).status_code==404
  raw,_=store.new_session(uid);c.cookies.set('clipbot_session',raw)
  assert c.get('/api/logs/sessions').json()['sessions'][0]['id']==sid
  assert c.get('/api/logs/sessions/'+sid).status_code==409
  DebugSessions(store).transition(uid,True,False,{'slots':1})
  result=c.get('/api/logs/sessions/'+sid)
  assert result.status_code==200 and result.headers['cache-control']=='no-store'
  assert result.headers['content-disposition'].startswith('attachment;')


def test_changes_are_recorded_without_splitting_session(tmp_path):
 store=Store(tmp_path/'changes.db');sessions=DebugSessions(store)
 cfg={'slots':2,'forced':[{'platform':'twitch','login':'one'}]}
 sid=sessions.transition('owner',False,True,cfg)
 sessions.transition('owner',True,True,{**cfg,'forced':[{'platform':'twitch','login':'two'}]})
 sessions.transition('owner',True,False,cfg)
 bundle=sessions.bundle('owner',sid)
 assert len(bundle['configurationChanges'])==2
 assert bundle['configurationChanges'][1]['configuration']['forced'][0]['login']=='two'
 assert len(sessions.list('owner'))==1
 sid2=sessions.transition('owner',False,True,cfg)
 assert sid2!=sid and sessions.bundle('owner',sid)['session']['state']=='stopped'

def test_session_event_limit_reports_truncation(tmp_path):
 sessions=DebugSessions(Store(tmp_path/'cap.db'));sid=sessions.transition('owner',False,True,{'slots':1})
 with sessions.store.connection(atomic=True) as db:
  db.executemany('INSERT INTO debug_session_events VALUES(?,?,?)',[(sid,n,json.dumps({'id':n})) for n in range(10001)])
 EventStore(sessions.store).record('owner','job_reported',stage='capturing')
 bundle=sessions.bundle('owner',sid)
 assert len(bundle['events'])==10000 and bundle['session']['droppedEvents']==1


def test_new_session_keeps_monitor_baseline_even_without_report_changes(tmp_path):
 from server.companion import CompanionStore
 store=Store(tmp_path/'baseline.db');CompanionStore(store);sessions=DebugSessions(store)
 report={'version':'0.2.5-beta','monitoredSources':[{'platform':'kick','login':'auto','state':'monitoring','started':1,'chatStatus':'connected','speechStatus':'active','cueStatus':'watching_for_cues'}]}
 with store.connection() as db:db.execute('INSERT INTO companion_state VALUES(?,?,?,?)',('device','owner',1,json.dumps(report)))
 sid=sessions.transition('owner',False,True,{'slots':1});sessions.transition('owner',True,False,{'slots':1})
 sid2=sessions.transition('owner',False,True,{'slots':1})
 bundle=sessions.bundle('owner',sid2)
 assert sid2!=sid
 assert bundle['session']['configuration']['companionVersion']=='0.2.5-beta'
 assert bundle['session']['configuration']['monitoredSources'][0]['login']=='auto'
