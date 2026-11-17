"""Account-owned intent and authenticated companion acknowledgments."""
import json,os,re,secrets,time
from urllib.parse import urlsplit
from .scouts import ScoutStore,limits_in,empty_config
from .worker_jobs import device_user
from .store import token_hash

ERRORS={None,'tools_missing','analysis_paused','beta_required','coverage_unavailable','connection_lost','processing_failed','trigger_settings_unavailable'}
class CompanionStore:
 def __init__(self,store):
  self.store=store;self.required_version=None;self.required_versions=None;ScoutStore(store)
  with store.connection() as db:db.execute("CREATE TABLE IF NOT EXISTS companion_state(device TEXT PRIMARY KEY,user_id TEXT NOT NULL,last_seen REAL NOT NULL,data TEXT NOT NULL)")
 @staticmethod
 def download():
  # Installer links are granted only by the authenticated release router.
  return {'available':False}
 def version_for(self,target):
  return self.required_versions(target) if self.required_versions else self.required_version
 def status(self,uid):
  with self.store.connection() as db:
   setting=db.execute('SELECT data,revision FROM scout_settings WHERE user_id=?',(uid,)).fetchone()
   row=db.execute("SELECT c.* FROM companion_state c JOIN worker_devices d ON d.token=c.device WHERE c.user_id=? AND d.user_id=? AND d.expires>? ORDER BY c.last_seen DESC LIMIT 1",(uid,uid,time.time())).fetchone()
  cfg=json.loads(setting['data']) if setting else empty_config();revision=setting['revision'] if setting else '';requested=cfg['running'];report=json.loads(row['data']) if row else {}
  fresh=bool(row and row['last_seen']>time.time()-90)
  if not fresh:state='offline'
  elif report.get('errorCode') or not report.get('ready'):state='attention'
  elif requested:state='running' if report.get('monitoring') and report.get('acknowledgedRevision')==revision else 'starting'
  else:state='ready' if not report.get('monitoring') and report.get('acknowledgedRevision')==revision else 'stopping'
  target=report.get('platformTarget','windows-x86_64')
  return {'state':state,'requestedRunning':requested,'revision':revision,'lastSeen':row['last_seen'] if fresh else None,'activeScouts':report.get('activeScouts',0) if fresh else 0,'hardwareSlots':report.get('hardwareSlots',2) if fresh else 2,'errorCode':report.get('errorCode') if fresh else None,'monitoredSources':report.get('monitoredSources',[]) if fresh and requested else [],'download':self.download(),'platformTarget':target,'requiredVersion':self.version_for(target),'companionVersion':report.get('version','0.2.0-beta') if fresh else None}
 def control(self,uid,running):
  if type(running) is not bool:raise ValueError('Choose Start or Stop.')
  status=self.status(uid)
  if running and status['state'] not in ('ready','running','starting'):raise ValueError('Connect a ready companion before starting ClipBot.')
  with self.store.connection(atomic=True) as db:
   setting=db.execute('SELECT data FROM scout_settings WHERE user_id=?',(uid,)).fetchone();cfg=json.loads(setting['data']) if setting else empty_config()
   if running:
    fresh=db.execute('SELECT c.data FROM companion_state c JOIN worker_devices d ON d.token=c.device WHERE c.user_id=? AND d.user_id=? AND d.expires>? AND c.last_seen>? ORDER BY c.last_seen DESC LIMIT 1',(uid,uid,time.time(),time.time()-90)).fetchone()
    report=json.loads(fresh['data']) if fresh else {}
    if not report.get('ready') or report.get('errorCode'):raise ValueError('Reconnect a ready companion before starting ClipBot.')
    target=report.get('platformTarget','windows-x86_64');required=self.version_for(target)
    if self.required_versions and target!='windows-x86_64' and not required:raise ValueError('The verified companion release for this platform is not available yet.')
    if required and report.get('version','0.2.0-beta')!=required:raise ValueError('Update the companion through Start ClipBot before starting monitoring.')
    limits=limits_in(db,uid);capacity=min(limits['scouts'],report['hardwareSlots'])
    if capacity<=0:raise ValueError('Active plan coverage is required to start ClipBot.')
    if not cfg['slots']:cfg['slots']=min(2,capacity)
    if cfg['slots']>limits['scouts'] or len(cfg['forced'])+len(cfg.get('forcedCategories',[]))>(40 if 'platformSlots' in cfg else cfg['slots']):raise ValueError('Update scout slots and forced channels for your current plan.')
   was_running=cfg['running']
   cfg['running']=running
   db.execute('INSERT OR REPLACE INTO scout_settings VALUES(?,?,?,?)',(uid,json.dumps(cfg),secrets.token_hex(16),time.time()))
   from .debug_sessions import DebugSessions
   DebugSessions.transition_in(db,uid,was_running,running,cfg)
  return self.status(uid)
 def report(self,token,data):
  fields={'ready','monitoring','acknowledgedRevision','hardwareSlots','activeScouts','errorCode'}
  if not isinstance(data,dict) or not fields<=set(data) or not set(data)<=fields|{'version','monitoredSources','platformTarget'} or any(type(data[k]) is not bool for k in ('ready','monitoring')) or type(data['hardwareSlots']) is not int or not 1<=data['hardwareSlots']<=40 or type(data['activeScouts']) is not int or not 0<=data['activeScouts']<=40 or data['errorCode'] not in ERRORS or not isinstance(data['acknowledgedRevision'],str) or not re.fullmatch(r'(?:[a-f0-9]{32})?',data['acknowledgedRevision']):raise ValueError('Invalid companion report.')
  from .companion_download import FILENAMES
  target=data.get('platformTarget','windows-x86_64')
  if not isinstance(target,str) or target not in FILENAMES:raise ValueError('Invalid companion platform.')
  if 'monitoredSources' in data:
   sources=data['monitoredSources']
   from .scouts import source_identity
   if not isinstance(sources,list) or len(sources)>40:raise ValueError('Invalid monitored sources.')
   for source in sources:
    if not isinstance(source,dict) or not {'platform','login','state','started','chatStatus','speechStatus','cueStatus'}<=set(source) or not set(source)<={'platform','login','state','started','chatStatus','speechStatus','cueStatus','trigger','interaction'}:raise ValueError('Invalid monitored source.')
    if 'interaction' in source:
     from .interaction import validate_interaction
     validate_interaction(source['interaction'],time.time())
    source_identity({k:source[k] for k in ('platform','login')})
    if source['state'] not in ('connecting','monitoring','reconnecting') or source['chatStatus'] not in ('connecting','connected','unavailable','disabled') or source['speechStatus'] not in ('active','waiting','unavailable','disabled') or source['cueStatus'] not in ('warming_up','watching_for_cues','saving_clip','waiting_for_processing') or type(source['started']) not in (int,float) or not 0<source['started']<=time.time()+60:raise ValueError('Invalid monitor status.')
    if source.get('trigger') not in (None,'manual','speech_phrase','chat_phrase','chat_spike','audio_rise'):raise ValueError('Invalid trigger status.')
   if len({(v['platform'],v['login']) for v in sources})!=len(sources):raise ValueError('Duplicate monitored sources.')
  if 'version' in data and (not isinstance(data['version'],str) or not re.fullmatch(r'[A-Za-z0-9._-]{1,40}',data['version'])):raise ValueError('Invalid companion version.')
  with self.store.connection(atomic=True) as db:
   uid=device_user(db,token);now=time.time()
   previous=db.execute('SELECT data FROM companion_state WHERE device=?',(token_hash(token),)).fetchone()
   previous=json.loads(previous['data']) if previous else {}
   if previous and previous.get('platformTarget','windows-x86_64')!=target:raise ValueError('Pair this computer again before changing its platform.')
   db.execute('INSERT OR REPLACE INTO companion_state VALUES(?,?,?,?)',(token_hash(token),uid,now,json.dumps(data)))
   db.execute('UPDATE worker_devices SET last_seen=? WHERE token=?',(now,token_hash(token)))
  from .pipeline_events import EventStore
  events=EventStore(self.store)
  if previous.get('version')!=data.get('version') and data.get('version'):
   events.emit(uid,'companion_reported',source='companion',details={'companionVersion':data['version']})
  old={(s['platform'],s['login']):s for s in previous.get('monitoredSources',[])}
  new={(s['platform'],s['login']):s for s in data.get('monitoredSources',[])}
  for key,source in new.items():
   fields={'monitorState':source['state'],'chatStatus':source['chatStatus'],'speechStatus':source['speechStatus']}
   prior=old.get(key,{})
   if any(prior.get(k)!=source[k] for k in ('state','chatStatus','speechStatus')):
    events.emit(uid,'monitor_connected',source='scouting',platform=key[0],login=key[1],details=fields)
  for key in old.keys()-new.keys():events.emit(uid,'monitor_removed',source='scouting',platform=key[0],login=key[1],level='warning')
  return {'ok':True}
