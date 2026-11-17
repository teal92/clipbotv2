"""Owner-gated initial live analysis, authenticated by the paired device."""
import hmac,json,time,os
from fastapi import APIRouter,Request,HTTPException
from pydantic import BaseModel,ConfigDict,Field,StrictBool,StrictInt,field_validator
from .worker_jobs import device_user,WorkerDenied
from .scouts import limits_in,ScoutStore
from .analysis import AnalysisService,AnalysisDenied,validate_personal_preferences,validate_capture_cue
from .budgets import BudgetDenied
from .admin import BETA_VERSION

class LiveSwitch(BaseModel):
    model_config=ConfigDict(extra='forbid')
    enabled:StrictBool
class AnalyzeWindow(BaseModel):
    model_config=ConfigDict(extra='forbid')
    jobId:str=Field(pattern=r'^[a-f0-9]{32}$')
    lease:str=Field(pattern=r'^[a-f0-9]{32}$')
    duration:float=Field(ge=15,le=305,allow_inf_nan=False)
    transcript:list[dict]=Field(min_length=1,max_length=200)
    captureCue:str|None=None
    personalPreferences:dict|None=None
    personalPreferencesRevision:StrictInt|None=Field(default=None,ge=0)

    @field_validator('captureCue')
    @classmethod
    def bounded_capture_cue(cls,value):
        return validate_capture_cue(value)

    @field_validator('personalPreferences')
    @classmethod
    def bounded_preferences(cls,value):
        if value is not None:validate_personal_preferences(value)
        return value

def test_enabled(store,admin_uid,uid):
    if not admin_uid or not hmac.compare_digest(admin_uid,uid):return False
    with store.connection() as db:row=db.execute("SELECT value FROM guards WHERE key='live_test_dispatch'").fetchone()
    if not row:return False
    try:data=json.loads(row['value']);return data['owner']==uid and data['expires']>time.time()
    except (KeyError,ValueError,TypeError):return False

def customer_enabled(store,uid):
    """Independent release gate; never accepts sandbox or owner readiness bypasses."""
    if os.getenv('CLIPBOT_CUSTOMER_ANALYSIS_ENABLED')!='1' or store.billing_mode!='live':return False
    from .billing_modes import entitlement_allowed
    from .legal import POLICY_VERSION
    with store.connection() as db:
        return bool(entitlement_allowed(db,uid) and
            db.execute('SELECT 1 FROM email_verification WHERE user_id=?',(uid,)).fetchone() and
            db.execute('SELECT 1 FROM legal_acceptances WHERE user_id=? AND version=?',(uid,POLICY_VERSION)).fetchone())

def build_analysis_router(store,current,ledger,admin_uid,analysis=None):
    router=APIRouter();analysis=analysis or AnalysisService(store,ledger)
    @router.get('/api/pipeline/test-status')
    def status(request:Request):
        uid=current(request)['user_id']
        return {'analysisEnabled':test_enabled(store,admin_uid,uid),'testCeilingMicros':50000,'publishingAutomatic':False}
    @router.post('/api/admin/pipeline-test')
    def enable(data:LiveSwitch,request:Request):
        uid=current(request,True)['user_id']
        if not admin_uid or not hmac.compare_digest(admin_uid,uid) or store.user(uid)['email']=='clipbot-local-development@example.invalid':raise HTTPException(403,'Owner access is required.')
        with store.connection(atomic=True) as db:
            if data.enabled:db.execute("INSERT OR REPLACE INTO guards VALUES('live_test_dispatch',?)",(json.dumps({'owner':uid,'expires':time.time()+3600}),))
            else:db.execute("DELETE FROM guards WHERE key='live_test_dispatch'")
        ledger.enabled=data.enabled
        return {'analysisEnabled':data.enabled,'expiresInSeconds':3600 if data.enabled else 0,'testCeilingMicros':50000}
    @router.post('/api/worker/analyze')
    def analyze(data:AnalyzeWindow,request:Request):
        header=request.headers.get('authorization','');token=header[7:] if header.startswith('Bearer ') else ''
        with store.connection() as db:
            try:uid=device_user(db,token)
            except WorkerDenied as error:raise HTTPException(401,str(error))
            job=db.execute("SELECT * FROM pipeline_jobs WHERE id=? AND user_id=? AND lease=? AND device=? AND lease_expires>? AND stage IN ('transcribing','analyzing','review')",(data.jobId,uid,data.lease,__import__('hashlib').sha256(token.encode()).hexdigest(),time.time())).fetchone()
        if not job:raise HTTPException(409,'Processing job or lease is unavailable.')
        def mark_failure(code):
            with store.connection(atomic=True) as db:db.execute("UPDATE pipeline_jobs SET stage='failed',error_code=?,updated=? WHERE id=? AND user_id=? AND lease=? AND stage IN ('transcribing','analyzing','review')",(code,time.time(),data.jobId,uid,data.lease))
        owner_test=test_enabled(store,admin_uid,uid)
        if not owner_test and not customer_enabled(store,uid):raise HTTPException(409,'Customer analysis is paused or account authorization is incomplete.')
        if owner_test and not store.beta_accepted(uid):raise HTTPException(428,'Acknowledge beta feedback in Davey before analysis.')
        progression=store.davey.status(uid)
        if data.personalPreferences is not None and (not progression['personalContext'] or data.personalPreferencesRevision!=progression['revision']):
            raise HTTPException(409,'Personal-context permission is missing or changed. Refresh the Companion.')
        if data.personalPreferences is None and data.personalPreferencesRevision is not None:raise HTTPException(409,'Personal context is unavailable.')
        selection_preferences=store.get_preferences(uid)
        ledger.enabled=True
        source=json.loads(job['source'])
        with store.connection(atomic=True) as db:db.execute("UPDATE pipeline_jobs SET stage='analyzing',updated=? WHERE id=? AND user_id=? AND lease=? AND stage='transcribing'",(time.time(),data.jobId,uid,data.lease))
        def authorize_dispatch():
            with store.connection(atomic=True) as db:
                if device_user(db,token)!=uid:raise AnalysisDenied('Worker access changed.')
                valid=db.execute("SELECT 1 FROM pipeline_jobs WHERE id=? AND user_id=? AND lease=? AND device=? AND lease_expires>? AND stage='analyzing'",(data.jobId,uid,data.lease,__import__('hashlib').sha256(token.encode()).hexdigest(),time.time())).fetchone()
                switch=db.execute("SELECT value FROM guards WHERE key='live_test_dispatch'").fetchone()
                enabled=json.loads(switch['value']) if switch else {}
                authorized=(enabled.get('owner')==uid and enabled.get('expires',0)>time.time() and store.beta_accepted(uid)) if owner_test else customer_enabled(store,uid)
                if not valid or not authorized or limits_in(db,uid)['scouts']<=0:raise AnalysisDenied('Analysis authorization was cancelled or expired.')
                settings,revision=store.davey._settings(db,uid)
                if store.davey._context_key(db,uid,settings)!=progression['contextKey'] or (data.personalPreferences is not None and (not settings['personalContext'] or revision!=data.personalPreferencesRevision)):
                    raise AnalysisDenied('Davey preferences changed.','analysis_preferences_changed')
                prefs=db.execute('SELECT data FROM preferences WHERE user_id=?',(uid,)).fetchone()
                if not prefs or json.loads(prefs['data']).get('usagePreset','paused')=='paused':raise AnalysisDenied('Davey activity was paused.','analysis_preferences_changed')
        controls=ScoutStore(store).controls(uid)
        try:result=analysis.analyze(uid,data.jobId,data.transcript,{'duration':data.duration,'platform':source['platform'],'creator':source['login'],'minClipSeconds':controls['minClipSeconds'],'maxClipSeconds':controls['maxClipSeconds'],'selectionPreferences':{'focus':selection_preferences.get('focus','balanced'),'avoid':selection_preferences.get('avoid','personal')},**({'captureCue':data.captureCue} if data.captureCue is not None else {})},authorize_dispatch=authorize_dispatch,personal_preferences=data.personalPreferences,scope_ceiling=50000 if owner_test else None,selection_context_key=progression['contextKey'])
        except BudgetDenied as error:
            code='analysis_busy' if 'throttled' in str(error) else 'review_limit' if 'review allowance' in str(error) else 'analysis_budget'
            mark_failure(code);raise HTTPException(409,{'code':code,'message':str(error)})
        except AnalysisDenied as error:
            mark_failure(error.code);raise HTTPException(409,{'code':error.code,'message':str(error)})
        with store.connection(atomic=True) as db:
            try:device_user(db,token)
            except WorkerDenied:raise HTTPException(401,'Worker access was revoked.')
            valid=db.execute("SELECT 1 FROM pipeline_jobs WHERE id=? AND user_id=? AND lease=? AND device=? AND lease_expires>? AND stage IN ('analyzing','review')",(data.jobId,uid,data.lease,__import__('hashlib').sha256(token.encode()).hexdigest(),time.time())).fetchone()
            if not valid:raise HTTPException(409,'Analysis finished but its job was cancelled or expired.')
            threshold={'loose':60,'balanced':75,'strict':90}[controls['sensitivity']]
            run=analysis.status(uid,data.jobId)
            outcome_code=(run['error_code'] if run and run['error_code']=='analysis_length_settings' else 'analysis_no_moment') if result is None else None
            rejected_details={}
            if result:
                seconds=round(result['end']-result['start'],6)
                rejected_details={'candidateScore':result['score'],'scoreThreshold':threshold,'candidateMillis':round(seconds*1000),'minClipSeconds':controls['minClipSeconds'],'maxClipSeconds':controls['maxClipSeconds']}
                if not controls['minClipSeconds']<=seconds<=controls['maxClipSeconds']:outcome_code='analysis_length_settings'
                elif result['score']<threshold:outcome_code='analysis_below_threshold'
                if outcome_code:result=None
            if result:
                candidate={**result,'id':data.jobId,'jobId':data.jobId,'platform':source['platform'],'creator':source['login'],'category':'','duration':f"{result['end']-result['start']:.0f}s",'belowThreshold':result['score']<75}
                db.execute('INSERT OR REPLACE INTO candidates VALUES(?,?,?)',(data.jobId,uid,json.dumps(candidate)))
            db.execute('UPDATE pipeline_jobs SET stage=?,updated=?,error_code=? WHERE id=? AND user_id=?',('review' if result else 'failed',time.time(),outcome_code,data.jobId,uid))
        if rejected_details and outcome_code:
            analysis.events.emit(uid,'analysis_rejected',job_id=data.jobId,source='analysis',stage='failed',code=outcome_code,level='info',details=rejected_details)
        run=analysis.status(uid,data.jobId)
        if result and run and run['context_key']:
            store.davey.prediction(uid,data.jobId,candidate,run['context_key'])
        return {'candidate':candidate if result else None,'stage':'review' if result else 'failed','outcomeCode':outcome_code,'personalContextUsed':bool(run and run['personal_context_used'])}
    return router,analysis
