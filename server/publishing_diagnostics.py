"""Bounded account-owned publishing bundles without captions, tokens or provider bodies."""
import json,logging,re,time,sys
from datetime import datetime,timezone
from fastapi import APIRouter,Request,HTTPException
from fastapi.responses import JSONResponse
logger=logging.getLogger('clipbot.publishing');logger.setLevel(logging.INFO);logger.propagate=False
if not logger.handlers:
 handler=logging.StreamHandler(sys.stdout);handler.setFormatter(logging.Formatter('%(message)s'));logger.addHandler(handler)
STATUS={'initializing','prepared','uploading','uploaded','finishing','unknown','published','failed'}
CODES={'initialization_unconfirmed','status_unconfirmed','provider_failed','provider_rejected','authorization_expired','upload_failed'}
def stamp(t):return datetime.fromtimestamp(t,timezone.utc).isoformat()
class PublishingDiagnostics:
 def __init__(self,store):
  self.store=store
  with store.connection() as db:
   db.execute('CREATE TABLE IF NOT EXISTS publishing_events(id INTEGER PRIMARY KEY AUTOINCREMENT,user_id TEXT NOT NULL,clip_id TEXT NOT NULL,data TEXT NOT NULL,created REAL NOT NULL)')
   db.execute('CREATE INDEX IF NOT EXISTS publishing_events_owner ON publishing_events(user_id,clip_id,created)')
 def record(self,uid,clip,attempt,platform,status,code=None,http_status=None):
  if not re.fullmatch('[a-f0-9]{32}',clip) or not re.fullmatch('[a-f0-9]{32}',attempt) or platform not in ('tiktok','instagram','facebook') or status not in STATUS or code is not None and code not in CODES:raise ValueError('Invalid publishing diagnostic.')
  if http_status is not None and (type(http_status) is not int or not 100<=http_status<=599):raise ValueError('Invalid provider HTTP status.')
  now=time.time();event={'clipId':clip,'attemptId':attempt,'platform':platform,'status':status,'createdAt':stamp(now)}
  if code:event['code']=code
  if http_status is not None:event['httpStatus']=http_status
  with self.store.connection() as db:
   db.execute('INSERT INTO publishing_events(user_id,clip_id,data,created) VALUES(?,?,?,?)',(uid,clip,json.dumps(event),now))
   db.execute('DELETE FROM publishing_events WHERE user_id=? AND (created<? OR id NOT IN (SELECT id FROM publishing_events WHERE user_id=? ORDER BY id DESC LIMIT 2000))',(uid,now-30*86400,uid))
  logger.info(json.dumps({'source':'publishing','level':'error' if code else 'info',**event}))
 def emit(self,*args,**kwargs):
  try:self.record(*args,**kwargs)
  except Exception:logging.getLogger('clipbot.publishing').warning('Publishing diagnostic storage unavailable')
 def list(self,uid):
  with self.store.connection() as db:rows=db.execute('SELECT clip_id,MIN(created) started,MAX(created) updated,COUNT(*) count FROM publishing_events WHERE user_id=? GROUP BY clip_id ORDER BY updated DESC LIMIT 20',(uid,)).fetchall()
  return [{'clipId':r['clip_id'],'startedAt':stamp(r['started']),'updatedAt':stamp(r['updated']),'events':r['count']} for r in rows]
 def bundle(self,uid,clip):
  with self.store.connection() as db:
   rows=db.execute('SELECT data FROM publishing_events WHERE user_id=? AND clip_id=? ORDER BY id LIMIT 2000',(uid,clip)).fetchall()
   posts=db.execute('SELECT id,platform,status,created,updated,receipt FROM publications WHERE user_id=? AND clip_id=?',(uid,clip)).fetchall() if db.execute("SELECT 1 FROM sqlite_master WHERE name='publications'").fetchone() else []
   worker=[]
   if db.execute("SELECT 1 FROM sqlite_master WHERE name='pipeline_events'").fetchone():worker=[json.loads(e['data']) for e in db.execute("SELECT data FROM pipeline_events WHERE user_id=? AND json_extract(data,'$.jobId')=? AND json_extract(data,'$.source')='publishing' ORDER BY id LIMIT 500",(uid,clip))]
   owned=db.execute('SELECT 1 FROM pipeline_jobs WHERE id=? AND user_id=?',(clip,uid)).fetchone() if db.execute("SELECT 1 FROM sqlite_master WHERE name='pipeline_jobs'").fetchone() else None
  if not rows and not posts and not owned:raise KeyError('Publishing bundle unavailable.')
  return {'format':'clipbot-publishing-session-v1','exportedAt':stamp(time.time()),'clipId':clip,'events':[json.loads(row['data']) for row in rows],'workerEvents':worker,'publications':[{'attemptId':p['id'],'platform':p['platform'],'status':p['status'],'createdAt':stamp(p['created']),'updatedAt':stamp(p['updated']),'providerConfirmed':bool(p['receipt'])} for p in posts],'privacy':'No credentials, captions, media links or provider response bodies included.'}
def build_publishing_logs_router(store,current):
 router=APIRouter();logs=PublishingDiagnostics(store)
 @router.get('/api/pipeline/publishing-logs')
 def listing(request:Request):return {'bundles':logs.list(current(request)['user_id'])}
 @router.get('/api/pipeline/publishing-logs/{clip_id}')
 def bundle(clip_id:str,request:Request):
  uid=current(request)['user_id']
  if not re.fullmatch('[a-f0-9]{32}',clip_id):raise HTTPException(404,'Publishing bundle unavailable.')
  try:data=logs.bundle(uid,clip_id)
  except KeyError:raise HTTPException(404,'Publishing bundle unavailable.') from None
  return JSONResponse(data,headers={'Content-Disposition':f'attachment; filename="clipbot-publishing-{clip_id}.json"'})
 return router
