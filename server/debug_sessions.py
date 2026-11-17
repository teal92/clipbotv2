"""Account-owned Start-to-Stop bundles; never stores arbitrary diagnostic text."""
import json,secrets,time,re
from datetime import datetime,timezone

def stamp(value):return datetime.fromtimestamp(value,timezone.utc).isoformat() if value else None

class DebugSessions:
 def __init__(self,store):
  self.store=store
  with store.connection() as db:self.initialize(db)
 @staticmethod
 def initialize(db):
  db.execute("CREATE TABLE IF NOT EXISTS debug_sessions(id TEXT PRIMARY KEY,user_id TEXT NOT NULL,started REAL NOT NULL,stopped REAL,configuration TEXT NOT NULL,dropped INTEGER NOT NULL DEFAULT 0)")
  db.execute("CREATE INDEX IF NOT EXISTS debug_sessions_owner ON debug_sessions(user_id,started)")
  db.execute("CREATE TABLE IF NOT EXISTS debug_session_configurations(session_id TEXT NOT NULL,created REAL NOT NULL,data TEXT NOT NULL)")
  db.execute("CREATE TABLE IF NOT EXISTS debug_session_events(session_id TEXT NOT NULL,event_id INTEGER NOT NULL,data TEXT NOT NULL,PRIMARY KEY(session_id,event_id))")
 @staticmethod
 def transition_in(db,uid,was_running,running,config):
  DebugSessions.initialize(db)
  active=db.execute('SELECT id FROM debug_sessions WHERE user_id=? AND stopped IS NULL ORDER BY started DESC LIMIT 1',(uid,)).fetchone()
  safe={key:config[key] for key in ('slots','platformSlots','forced','favorites','categories','forcedCategories') if key in config}
  if running:
   if active:
    last=db.execute('SELECT data FROM debug_session_configurations WHERE session_id=? ORDER BY created DESC LIMIT 1',(active['id'],)).fetchone()
    if not last or json.loads(last['data'])!=safe:
     db.execute('INSERT INTO debug_session_configurations VALUES(?,?,?)',(active['id'],time.time(),json.dumps(safe)))
     db.execute('DELETE FROM debug_session_configurations WHERE session_id=? AND rowid NOT IN (SELECT rowid FROM debug_session_configurations WHERE session_id=? ORDER BY created DESC LIMIT 200)',(active['id'],active['id']))
    return active['id']
   sid=secrets.token_hex(16)
   # Only already-validated selection fields enter a bundle, never account or device tokens.
   initial=dict(safe)
   if db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='companion_state'").fetchone():
    report=db.execute('SELECT data FROM companion_state WHERE user_id=? ORDER BY last_seen DESC LIMIT 1',(uid,)).fetchone()
    baseline=json.loads(report['data']) if report else {}
    version=baseline.get('version')
    initial['monitoredSources']=[{k:v for k,v in source.items() if k in ('platform','login','state','started','chatStatus','speechStatus','cueStatus','trigger')} for source in baseline.get('monitoredSources',[])]
    if isinstance(version,str) and re.fullmatch(r'[0-9]+\.[0-9]+\.[0-9]+(?:-beta)?',version):initial['companionVersion']=version
   db.execute('INSERT INTO debug_sessions(id,user_id,started,configuration) VALUES(?,?,?,?)',(sid,uid,time.time(),json.dumps(initial)))
   db.execute('INSERT INTO debug_session_configurations VALUES(?,?,?)',(sid,time.time(),json.dumps(safe)))
   old=db.execute('SELECT id FROM debug_sessions WHERE user_id=? ORDER BY started DESC LIMIT -1 OFFSET 20',(uid,)).fetchall()
   for row in old:
    db.execute('DELETE FROM debug_session_configurations WHERE session_id=?',(row['id'],));db.execute('DELETE FROM debug_session_events WHERE session_id=?',(row['id'],));db.execute('DELETE FROM debug_sessions WHERE id=?',(row['id'],))
   return sid
  if active:
   db.execute('UPDATE debug_sessions SET stopped=? WHERE id=?',(time.time(),active['id']))
   return active['id']
  return None
 def transition(self,uid,was_running,running,config):
  with self.store.connection(atomic=True) as db:return self.transition_in(db,uid,was_running,running,config)
 @staticmethod
 def record_in(db,uid,event):
  DebugSessions.initialize(db)
  row=db.execute('SELECT id FROM debug_sessions WHERE user_id=? AND stopped IS NULL ORDER BY started DESC LIMIT 1',(uid,)).fetchone()
  if not row:return
  sid=row['id'];db.execute('INSERT OR IGNORE INTO debug_session_events VALUES(?,?,?)',(sid,event['id'],json.dumps(event)))
  count=db.execute('SELECT COUNT(*) FROM debug_session_events WHERE session_id=?',(sid,)).fetchone()[0]
  if count>10000:
   db.execute('DELETE FROM debug_session_events WHERE session_id=? AND event_id IN (SELECT event_id FROM debug_session_events WHERE session_id=? ORDER BY event_id LIMIT ?)',(sid,sid,count-10000))
   db.execute('UPDATE debug_sessions SET dropped=dropped+? WHERE id=?',(count-10000,sid))
 @staticmethod
 def summary(row):return {'id':row['id'],'startedAt':stamp(row['started']),'stoppedAt':stamp(row['stopped']),'state':'stopped' if row['stopped'] else 'running','configuration':json.loads(row['configuration']),'droppedEvents':row['dropped']}
 def list(self,uid):
  with self.store.connection() as db:rows=db.execute('SELECT * FROM debug_sessions WHERE user_id=? ORDER BY started DESC LIMIT 20',(uid,)).fetchall()
  return [self.summary(row) for row in rows]
 def bundle(self,uid,sid):
  with self.store.connection() as db:
   row=db.execute('SELECT * FROM debug_sessions WHERE id=? AND user_id=?',(sid,uid)).fetchone()
   if not row:raise KeyError('Session not found.')
   changes=db.execute('SELECT created,data FROM debug_session_configurations WHERE session_id=? ORDER BY created',(sid,)).fetchall()
   events=db.execute('SELECT data FROM debug_session_events WHERE session_id=? ORDER BY event_id',(sid,)).fetchall()
  return {'format':'clipbot-debug-session-v1','exportedAt':stamp(time.time()),'session':self.summary(row),'configurationChanges':[{'createdAt':stamp(c['created']),'configuration':json.loads(c['data'])} for c in changes],'events':[json.loads(e['data']) for e in events],'privacy':'No credentials, media links, transcript text or chat messages are included.'}
