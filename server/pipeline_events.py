"""Bounded account-owned diagnostics built exclusively from allowlisted tokens."""
import json,logging,re,sys,time
from datetime import datetime,timezone

TEMPLATES={
 'scout_settings_changed':'Scout selections updated','monitor_connected':'Companion stream state changed','monitor_removed':'Companion stopped monitoring stream','companion_reported':'Companion version reported',
 'job_enqueued':'Capture window queued', 'job_opened':'Scout window opened', 'job_claimed':'Worker claimed queued window',
 'job_reported':'Worker processing stage updated', 'job_resumed':'Worker resumed verified window', 'job_cancelled':'Processing cancelled',
 'analysis_counting':'Davey input token check started','analysis_counted':'Davey input token check completed',
 'analysis_dispatch':'Davey paid analysis dispatched once','analysis_response':'Davey provider response received',
 'analysis_selected':'Davey returned a valid candidate for settings checks','analysis_no_candidate':'Davey found no complete candidate',
 'analysis_rejected':'Clip did not pass your selection settings','analysis_error':'Davey analysis stopped','analysis_budget_denied':'Analysis budget or coverage guard refused dispatch',
 'analysis_input_rejected':'Transcript input rejected before paid dispatch',
 'transcription_started':'Local transcription started','transcription_completed':'Local transcription completed',
 'render_started':'Local preview rendering started','render_completed':'Local preview rendering verified',
 'render_failed':'Local preview rendering failed','preview_ready':'Playable preview ready',
 'preview_failed':'Playable preview verification failed','upload_started':'Media upload started',
 'upload_failed':'Media upload failed','worker_request_failed':'Worker service request failed'}
STAGES=frozenset({'queued','capturing','transcribing','analyzing','review','rendering','ready','publishing','published','failed','cancelled'})
CODES=frozenset({'analysis_no_moment','analysis_below_threshold','analysis_length_settings','render_invalid_range','render_source_unavailable','render_encode_failed','render_verify_failed','render_timeout','render_tool_missing','capture_unavailable','disk_low','processing_failed','cancelled','transcription_unavailable','dependency_mismatch','queue_full','no_speech','not_selected','analysis_busy','review_limit','analysis_budget','analysis_failed','analysis_invalid_json','analysis_invalid_schema','analysis_invalid_range','analysis_invalid_metadata','analysis_incomplete','analysis_provider_auth','analysis_provider_rate_limit','analysis_provider_unavailable','analysis_provider_timeout','analysis_usage_unknown','analysis_invalid_transcript','analysis_configuration','analysis_input_limit','analysis_invalid_preferences'})
CODES=CODES|{'service_rate_limited','analysis_request_invalid','analysis_authorization','service_unavailable','service_timeout','analysis_invalid_cue','analysis_preferences_changed'}
logger=logging.getLogger('clipbot.pipeline')
logger.setLevel(logging.INFO)
logger.propagate=False
if not logger.handlers:
    handler=logging.StreamHandler(sys.stdout);handler.setFormatter(logging.Formatter('%(message)s'));logger.addHandler(handler)

class EventStore:
    def __init__(self,store):
        self.store=store
        with store.connection() as db:
            db.execute('CREATE TABLE IF NOT EXISTS pipeline_events(id INTEGER PRIMARY KEY AUTOINCREMENT,user_id TEXT NOT NULL,data TEXT NOT NULL,created REAL NOT NULL)')
            db.execute('CREATE INDEX IF NOT EXISTS pipeline_events_owner ON pipeline_events(user_id,id)')
    def record(self,uid,event,*,job_id=None,stage=None,code=None,platform=None,login=None,elapsed_ms=None,source='pipeline',level='info',details=None):
        if event not in TEMPLATES or source not in ('pipeline','worker','analysis','transcription','rendering','capture','scouting','companion','processing','davey','publishing','service') or level not in ('info','warn','warning','error'):raise ValueError('Invalid diagnostic event.')
        if stage is not None and stage not in STAGES or code is not None and code not in CODES:raise ValueError('Invalid diagnostic status.')
        if platform is not None and platform not in ('twitch','kick','youtube'):raise ValueError('Invalid diagnostic platform.')
        if job_id is not None and (not isinstance(job_id,str) or not re.fullmatch(r'[a-zA-Z0-9_-]{1,80}',job_id)):raise ValueError('Invalid diagnostic job.')
        if login is not None and (not isinstance(login,str) or not re.fullmatch(r'[a-zA-Z0-9_-]{1,35}',login)):raise ValueError('Invalid diagnostic creator.')
        if elapsed_ms is not None and (type(elapsed_ms) is not int or not 0<=elapsed_ms<=86400000):raise ValueError('Invalid diagnostic timing.')
        from .diagnostic_details import validate_diagnostic_details
        safe_details=validate_diagnostic_details(details) if details is not None else {}
        now=time.time();level='warning' if level=='warn' else level
        source={'pipeline':'processing','worker':'service','analysis':'davey'}.get(source,source)
        data={'event':event,'level':level,'source':source,'message':TEMPLATES[event],'createdAt':datetime.fromtimestamp(now,timezone.utc).isoformat()}
        if safe_details:data['details']=safe_details
        for key,value in [('jobId',job_id),('stage',stage),('code',code),('platform',platform),('login',login),('elapsedMs',elapsed_ms)]:
            if value is not None:data[key]=value
        if job_id:data['message']+=' | job '+job_id
        if platform and login:data['message']+=' | '+platform+' / '+login
        if elapsed_ms is not None:data['message']+=' | '+str(elapsed_ms)+' ms'
        if stage:data['message']+=': '+stage
        if code:data['message']+=' ('+code+')'
        with self.store.connection(atomic=True) as db:
            result=db.execute('INSERT INTO pipeline_events(user_id,data,created) VALUES(?,?,?)',(uid,json.dumps(data),now));data['id']=result.lastrowid
            from .debug_sessions import DebugSessions
            DebugSessions.record_in(db,uid,data)
            db.execute('DELETE FROM pipeline_events WHERE user_id=? AND (created<? OR id NOT IN (SELECT id FROM pipeline_events WHERE user_id=? ORDER BY id DESC LIMIT 500))',(uid,now-7*86400,uid))
        logger.log({'info':logging.INFO,'warning':logging.WARNING,'error':logging.ERROR}[level],json.dumps(data,separators=(',',':')))
        return data
    def emit(self,uid,event,**fields):
        # Diagnostics must never alter paid-dispatch or lease semantics.
        try:return self.record(uid,event,**fields)
        except Exception:
            logger.warning('{"event":"diagnostic_write_failed","level":"warning","source":"pipeline","message":"Pipeline diagnostic storage unavailable"}')
            return None
    def snapshot(self,uid,cursor=0,limit=200):
        if type(cursor) is not int or cursor<0 or type(limit) is not int or not 1<=limit<=500:raise ValueError('Invalid diagnostic pagination.')
        with self.store.connection() as db:
            if cursor:
                rows=db.execute('SELECT id,data FROM pipeline_events WHERE user_id=? AND id>? AND created>=? ORDER BY id LIMIT ?',(uid,cursor,time.time()-7*86400,limit)).fetchall()
            else:
                rows=list(reversed(db.execute('SELECT id,data FROM pipeline_events WHERE user_id=? AND created>=? ORDER BY id DESC LIMIT ?',(uid,time.time()-7*86400,limit)).fetchall()))
        return [{**json.loads(row['data']),'id':row['id']} for row in rows]
