"""Session-reviewed posts; upload grants are available only to paired devices."""
import json,re,time
from fastapi import APIRouter,Request,HTTPException,Query
from pydantic import BaseModel,ConfigDict,Field,StrictBool
from .publication import PublicationService,PublicationDenied
from .worker_jobs import device_user,WorkerDenied
from .store import token_hash

class AttemptRequest(BaseModel):
    model_config=ConfigDict(extra='forbid')
    attemptId:str=Field(pattern=r'^[a-f0-9]{32}$')
class ReadyArtifact(BaseModel):
    model_config=ConfigDict(extra='forbid')
    jobId:str=Field(pattern=r'^[a-f0-9]{32}$')
    lease:str=Field(pattern=r'^[a-f0-9]{32}$')
    artifact:dict
    previewToken:str=Field(pattern=r'^[a-f0-9]{64}$')
class CandidatePreview(BaseModel):
    model_config=ConfigDict(extra='forbid')
    jobId:str=Field(pattern=r'^[a-f0-9]{32}$')
    lease:str=Field(pattern=r'^[a-f0-9]{32}$')
    previewToken:str=Field(pattern=r'^[a-f0-9]{64}$')
class PublishChoice(BaseModel):
    model_config=ConfigDict(extra='forbid')
    clipId:str=Field(pattern=r'^[a-f0-9]{32}$')
    platform:str=Field(pattern=r'^(facebook|instagram|tiktok)$')
    options:dict

def build_publication_router(store,current,oauth):
    router=APIRouter();pub=PublicationService(store,oauth)
    from .publishing_diagnostics import build_publishing_logs_router
    router.include_router(build_publishing_logs_router(store,current))
    def device(request):
        header=request.headers.get('authorization','');token=header[7:] if header.startswith('Bearer ') else ''
        with store.connection() as db:
            try:uid=device_user(db,token)
            except WorkerDenied as error:raise HTTPException(401,str(error))
        return uid,token
    @router.post('/api/worker/davey-dispatch')
    def davey_dispatch(request:Request):
        uid,token=device(request)
        try:return pub.automation.dispatch(uid,token)
        except PublicationDenied as error:raise HTTPException(409,str(error)) from None
    @router.get('/api/pipeline/publications')
    def list_posts(request:Request):return {'publications':pub.snapshot(current(request)['user_id'])}
    @router.get('/api/pipeline/tiktok-settings')
    def tiktok(request:Request):
        uid=current(request)['user_id']
        try:return pub.creator_info(uid)
        except Exception:
            # Never expose provider exception text or response objects.
            raise HTTPException(409,'TikTok creator settings could not be loaded.') from None
    @router.post('/api/pipeline/publish')
    def publish(data:PublishChoice,request:Request):
        uid=current(request,True)['user_id']
        with store.connection() as db:review=db.execute('SELECT data FROM reviews WHERE user_id=? AND candidate_id=?',(uid,data.clipId)).fetchone()
        if not review or json.loads(review['data'])['user_feedback']['decision']!='approve':raise HTTPException(409,'Approve this candidate in Clips before publishing.')
        try:return pub.prepare(uid,data.clipId,data.platform,data.options)
        except PublicationDenied as error:raise HTTPException(409,str(error))
    @router.post('/api/pipeline/publications/{attempt_id}/reconcile')
    def reconcile(attempt_id:str,request:Request):
        uid=current(request,True)['user_id']
        try:return pub.reconcile(uid,attempt_id)
        except PublicationDenied as error:raise HTTPException(409,str(error))
    @router.get('/api/worker/jobs/{job_id}')
    def job_status(job_id:str,request:Request):
        uid,token=device(request)
        with store.connection() as db:
            row=db.execute('SELECT * FROM pipeline_jobs WHERE id=? AND user_id=?',(job_id,uid)).fetchone()
            if not row:raise HTTPException(404,'Job not found.')
            candidate=db.execute('SELECT data FROM candidates WHERE id=? AND user_id=?',(job_id,uid)).fetchone()
        return {'job':{'id':row['id'],'source':json.loads(row['source']),'stage':row['stage']},'candidate':json.loads(candidate['data']) if candidate else None,'publications':[p for p in pub.snapshot(uid) if p['clipId']==job_id]}
    @router.get('/api/worker/feedback-owner')
    def feedback_owner(request:Request,candidateId:str=Query(pattern=r'^[a-f0-9]{32}$')):
        uid,token=device(request)
        with store.connection(atomic=True) as db:
            try:device_user(db,token)
            except WorkerDenied:raise HTTPException(401,'Worker access was revoked.') from None
            row=db.execute('SELECT 1 FROM candidates c JOIN candidate_previews p ON p.user_id=c.user_id AND p.job_id=c.id WHERE c.id=? AND c.user_id=? AND p.device=?',(candidateId,uid,token_hash(token))).fetchone()
            if not row:raise HTTPException(404,'Local feedback candidate is unavailable.')
        return {'userId':uid,'candidateId':candidateId}
    @router.post('/api/worker/candidate-preview-ready')
    def candidate_preview(data:CandidatePreview,request:Request):
        uid,token=device(request)
        with store.connection(atomic=True) as db:
            device_user(db,token)
            from .billing_modes import entitlement_allowed
            if not entitlement_allowed(db,uid):raise HTTPException(409,'An active subscription is required to register clip previews.')
            row=db.execute("SELECT 1 FROM pipeline_jobs WHERE id=? AND user_id=? AND lease=? AND device=? AND lease_expires>? AND stage='review'",(data.jobId,uid,data.lease,token_hash(token),time.time())).fetchone()
            if not row:raise HTTPException(409,'Candidate preview lease is unavailable.')
            db.execute('INSERT OR REPLACE INTO candidate_previews VALUES(?,?,?,?,?)',(uid,data.jobId,token_hash(token),data.previewToken,time.time()))
        return {'ok':True}
    @router.post('/api/worker/render-ready')
    def rendered(data:ReadyArtifact,request:Request):
        uid,token=device(request)
        metadata={**data.artifact,'previewToken':data.previewToken}
        try:pub.validate_artifact(metadata)
        except PublicationDenied as error:raise HTTPException(422,str(error))
        if type(metadata.get('width')) is not int or type(metadata.get('height')) is not int or (metadata.get('width'),metadata.get('height'),metadata.get('framing'))!=(1080,1920,'blurred_fit'):raise HTTPException(422,'A captioned mobile render is required.')
        with store.connection(atomic=True) as db:
            try:device_user(db,token)
            except WorkerDenied:raise HTTPException(401,'Worker access was revoked.')
            from .billing_modes import entitlement_allowed
            if not entitlement_allowed(db,uid):raise HTTPException(409,'An active subscription is required to register rendered clips.')
            row=db.execute("SELECT stage FROM pipeline_jobs WHERE id=? AND user_id=? AND lease=? AND device=? AND lease_expires>? AND stage IN ('review','rendering')",(data.jobId,uid,data.lease,token_hash(token),time.time())).fetchone()
            if not row:raise HTTPException(409,'Rendering lease is unavailable.')
            if db.execute('SELECT 1 FROM publications WHERE clip_id=? AND user_id=?',(data.jobId,uid)).fetchone():raise HTTPException(409,'This artifact is already locked for publishing.')
            review_render=row['stage']=='review';stage='review' if review_render else 'ready'
            db.execute('INSERT OR REPLACE INTO clip_artifacts VALUES(?,?,?)',(uid,data.jobId,json.dumps(metadata)))
            db.execute('UPDATE pipeline_jobs SET stage=?,updated=? WHERE id=? AND user_id=?',(stage,time.time(),data.jobId,uid))
            if review_render:db.execute('INSERT OR REPLACE INTO candidate_previews VALUES(?,?,?,?,?)',(uid,data.jobId,token_hash(token),data.previewToken,time.time()))
        from .pipeline_events import EventStore
        EventStore(store).emit(uid,'preview_ready',job_id=data.jobId,stage=stage,source='rendering')
        return {'ok':True,'stage':stage}
    @router.post('/api/worker/diagnostic')
    def diagnostic(data:dict,request:Request):
        uid,token=device(request)
        if set(data)-{'event','jobId','lease','stage','code','elapsedMs','source','level','details'}:raise HTTPException(422,'Invalid diagnostic fields.')
        from .pipeline_events import EventStore
        with store.connection() as db:
            row=db.execute('SELECT source FROM pipeline_jobs WHERE id=? AND user_id=? AND lease=? AND device=?',(data.get('jobId'),uid,data.get('lease'),token_hash(token))).fetchone()
        if not row:raise HTTPException(409,'Diagnostic job is unavailable.')
        source=json.loads(row['source'])
        try:EventStore(store).record(uid,data.get('event'),job_id=data.get('jobId'),stage=data.get('stage'),code=data.get('code'),elapsed_ms=data.get('elapsedMs'),source=data.get('source','processing'),level=data.get('level','info'),platform=source['platform'],login=source['login'],details=data.get('details'))
        except (ValueError,TypeError):raise HTTPException(422,'Invalid diagnostic event.') from None
        return {'ok':True}
    @router.get('/api/worker/state')
    def worker_state(request:Request):
        uid,token=device(request)
        with store.connection() as db:
            jobs=[]
            for r in db.execute("SELECT id,source,stage,lease_expires FROM pipeline_jobs WHERE user_id=? ORDER BY CASE WHEN stage IN ('transcribing','analyzing','review','rendering','ready') THEN 0 ELSE 1 END, created DESC LIMIT 100",(uid,)):
                artifact=db.execute('SELECT data FROM clip_artifacts WHERE user_id=? AND clip_id=?',(uid,r['id'])).fetchone()
                candidate=db.execute('SELECT data FROM candidates WHERE user_id=? AND id=?',(uid,r['id'])).fetchone()
                run=db.execute('SELECT status FROM analysis_runs WHERE user_id=? AND job_id=?',(uid,r['id'])).fetchone()
                jobs.append({'id':r['id'],'source':json.loads(r['source']),'stage':r['stage'],'leaseExpires':r['lease_expires'],'artifact':json.loads(artifact['data']) if artifact else None,'candidate':json.loads(candidate['data']) if candidate else None,'analysisStatus':run['status'] if run else None})
        return {'userId':uid,'jobs':jobs,'publications':pub.snapshot(uid),'davey':store.davey.status(uid),'preferences':store.get_preferences(uid)}
    @router.post('/api/worker/upload-grant')
    def grant(data:AttemptRequest,request:Request):
        uid,token=device(request)
        try:return pub.grant(token,data.attemptId)
        except PublicationDenied as error:raise HTTPException(409,str(error))
    @router.post('/api/worker/uploaded')
    def uploaded(data:AttemptRequest,request:Request):
        uid,token=device(request)
        try:return pub.uploaded(token,data.attemptId)
        except (PublicationDenied,WorkerDenied) as error:raise HTTPException(409,str(error))
    @router.post('/api/worker/publication-status')
    def worker_reconcile(data:AttemptRequest,request:Request):
        uid,token=device(request)
        try:return pub.reconcile(uid,data.attemptId)
        except PublicationDenied as error:raise HTTPException(409,str(error))
    return router,pub
