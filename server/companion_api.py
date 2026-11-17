import os
from typing import Literal
from fastapi import APIRouter,Request,HTTPException
from pydantic import BaseModel,ConfigDict,StrictBool,Field
from .companion import CompanionStore

class Control(BaseModel):
 model_config=ConfigDict(extra='forbid')
 running:StrictBool

class BetaDownloadAcceptance(BaseModel):
 model_config=ConfigDict(extra='forbid')
 version:str=Field(pattern=r'^[A-Za-z0-9._-]{1,40}$')
 sha256:str=Field(pattern=r'^[a-f0-9]{64}$')
 acknowledged:StrictBool
 target:Literal['windows-x86_64','macos-arm64','macos-x86_64','linux-x86_64']='windows-x86_64'

def build_companion_router(store,current,is_owner=lambda session:False,access=None,oauth=None,billing=None):
 router=APIRouter();companion=CompanionStore(store);companion.required_version='0.2.7-beta'
 from .companion_releases import ReleaseCatalog
 catalog=ReleaseCatalog(store.path.parent)
 companion.required_version=catalog.required_version('windows-x86_64') or companion.required_version
 def select(target):
  try:return catalog.installer(target)
  except ValueError:raise HTTPException(422,'Choose a supported companion platform.') from None
 companion.required_versions=lambda target:catalog.required_version(target) or (companion.required_version if target=='windows-x86_64' else None)
 public_release=os.getenv('CLIPBOT_COMPANION_PUBLIC_RELEASE','0')=='1'
 unsigned_beta=os.getenv('CLIPBOT_COMPANION_UNSIGNED_BETA','0')=='1'
 with store.connection() as db:
  db.execute('CREATE TABLE IF NOT EXISTS companion_beta_acceptances(user_id TEXT NOT NULL,version TEXT NOT NULL,sha256 TEXT NOT NULL,accepted REAL NOT NULL,PRIMARY KEY(user_id,version,sha256))')
 def released(installer):return public_release and installer.ready() and (installer.production_ready or unsigned_beta and installer.beta_ready)
 def beta_required(uid,installer):
  if not installer.beta_ready:return False
  with store.connection() as db:return not db.execute('SELECT 1 FROM companion_beta_acceptances WHERE user_id=? AND version=? AND sha256=?',(uid,installer.metadata.get('version'),installer.metadata.get('sha256'))).fetchone()
 @router.get('/api/companion/status')
 def status(request:Request,target:str|None=None):
  session=current(request);result=companion.status(session['user_id'])
  installer=select(target or result['platformTarget'])
  owner=is_owner(session)
  def visible(item):return item.ready() and (owner or (released(item) and access is not None and access.readiness(session['user_id'])['ready']))
  def metadata(item):
   value={**item.metadata,'target':item.target}
   if item.beta_ready:value.update(unsignedBeta=True,requiresBetaAcceptance=not owner and beta_required(session['user_id'],item))
   return value
  result['downloads']=[metadata(item) for item in catalog.releases.values() if visible(item)]
  if visible(installer):result['download']=metadata(installer)
  return result
 @router.get('/api/companion/download')
 def download(request:Request,target:str='windows-x86_64'):
  session=current(request)
  installer=select(target)
  if not is_owner(session):
   if not public_release:raise HTTPException(403,'The customer companion release is not available yet.')
   if not released(installer):raise HTTPException(503,'The verified companion release is being prepared.')
   if access is None or not access.readiness(session['user_id'])['ready']:raise HTTPException(428,'Verify your email and accept the current policies before downloading.')
   if beta_required(session['user_id'],installer):raise HTTPException(428,'Read and acknowledge the unsigned beta notice before downloading this version.')
  return installer.response()
 @router.post('/api/companion/beta-accept')
 def accept_beta(data:BetaDownloadAcceptance,request:Request):
  session=current(request,True);uid=session['user_id']
  installer=select(data.target)
  if access is None or not access.readiness(uid)['ready']:raise HTTPException(428,'Verify your email and accept the current policies before downloading.')
  if not released(installer) or not unsigned_beta or not installer.beta_ready:raise HTTPException(409,'The unsigned beta download is not enabled.')
  if not data.acknowledged:raise HTTPException(422,'Read and acknowledge the unsigned beta notice before downloading.')
  if data.version!=installer.metadata['version'] or data.sha256!=installer.metadata['sha256']:raise HTTPException(409,'The installer changed. Refresh and read its current notice.')
  import time
  with store.connection(atomic=True) as db:
   db.execute('INSERT OR IGNORE INTO companion_beta_acceptances VALUES(?,?,?,?)',(uid,data.version,data.sha256,time.time()))
  return {'ok':True}
 @router.post('/api/companion/control')
 def control(data:Control,request:Request):
  session=current(request,True);uid=session['user_id']
  if data.running and not is_owner(session):
   if access is None or not access.readiness(uid)['ready']:
    raise HTTPException(428,'Verify your email and accept the current policies in Account before starting ClipBot.')
   from .connections import connection_status
   platforms=connection_status(store,uid,oauth)['platforms']
   if not any(p['id'] in ('twitch','kick') and p.get('connected') is True and p.get('status')=='connected' and p.get('monitoringReady',True) is True for p in platforms):
    raise HTTPException(409,'Connect Twitch or Kick before starting ClipBot.')
   subscription=store.billing_status(uid)
   import time
   if not billing or not billing.live or not subscription or subscription['status']!='active' or subscription['expires']<=time.time() or not store.coverage(uid):
    raise HTTPException(409,'Choose an active paid subscription in Plans and Billing before starting ClipBot.')
  try:return companion.control(uid,data.running)
  except ValueError as error:raise HTTPException(409,str(error))
 @router.post('/api/worker/companion-heartbeat')
 def heartbeat(data:dict,request:Request):
  header=request.headers.get('authorization','');token=header[7:] if header.startswith('Bearer ') else ''
  try:return companion.report(token,data)
  except ValueError:raise HTTPException(401,'Reconnect the companion or check its status report.') from None
 return router,companion
