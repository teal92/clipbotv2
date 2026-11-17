"""Atomic edits: local rendering is required before changing an owned candidate."""
import json,math,secrets,time
from fastapi import APIRouter,HTTPException,Request
from pydantic import BaseModel,ConfigDict,Field
from .worker_jobs import device_user,WorkerDenied
from .store import token_hash
from .publication import PublicationService,PublicationDenied

class EditJob(BaseModel):
    model_config=ConfigDict(extra='forbid')
    jobId:str=Field(pattern=r'^[a-f0-9]{32}$')

class BeginEdit(EditJob):
    lease:str=Field(pattern=r'^[a-f0-9]{32}$')
    previewToken:str=Field(pattern=r'^[a-f0-9]{64}$')
    title:str=Field(min_length=1,max_length=100)
    description:str=Field(min_length=1,max_length=1000)
    start:float=Field(strict=True,allow_inf_nan=False,ge=0,le=305)
    end:float=Field(strict=True,allow_inf_nan=False,ge=0,le=305)

class EditIdentity(EditJob):
    editId:str=Field(pattern=r'^[a-f0-9]{32}$')

class CompleteEdit(EditIdentity):
    artifact:dict
    previewToken:str=Field(pattern=r'^[a-f0-9]{64}$')

def build_clip_edit_router(store):
    router=APIRouter()
    with store.connection() as db:
        db.execute("CREATE TABLE IF NOT EXISTS clip_edits(user_id TEXT NOT NULL,job_id TEXT NOT NULL,edit_id TEXT NOT NULL,device TEXT NOT NULL,candidate TEXT NOT NULL,status TEXT NOT NULL,completed TEXT,PRIMARY KEY(user_id,job_id))")
    def device(request,db):
        header=request.headers.get('authorization','');token=header[7:] if header.startswith('Bearer ') else ''
        try:return device_user(db,token),token_hash(token)
        except WorkerDenied as error:raise HTTPException(401,str(error)) from None
    def require_edit_access(db,uid):
        from .billing_modes import entitlement_allowed
        if not entitlement_allowed(db,uid):raise HTTPException(409,'An active subscription is required to edit clips.')
    @router.post('/api/worker/clip-edits/begin')
    def begin(data:BeginEdit,request:Request):
        now=time.time()
        with store.connection(atomic=True) as db:
            uid,device_id=device(request,db)
            require_edit_access(db,uid)
            row=db.execute("SELECT c.data FROM candidates c JOIN pipeline_jobs j ON j.id=c.id AND j.user_id=c.user_id JOIN candidate_previews p ON p.job_id=j.id AND p.user_id=j.user_id WHERE c.id=? AND c.user_id=? AND j.stage='review' AND j.device=? AND j.lease=? AND j.lease_expires>? AND p.device=? AND p.token=?",(data.jobId,uid,device_id,data.lease,now,device_id,data.previewToken)).fetchone()
            if not row:raise HTTPException(409,'This preview changed or is unavailable for editing. Reopen the clip.')
            if db.execute('SELECT 1 FROM reviews WHERE user_id=? AND candidate_id=?',(uid,data.jobId)).fetchone() or db.execute('SELECT 1 FROM publications WHERE user_id=? AND clip_id=?',(uid,data.jobId)).fetchone():raise HTTPException(409,'Only an undecided clip can be edited. Publishing media is locked.')
            candidate=json.loads(row['data']);left=candidate.get('start');right=candidate.get('end')
            if any(type(v) not in (int,float) or not math.isfinite(v) for v in (left,right)) or not 0<=left<=data.start<data.end<=right<=305 or not 15<=round(data.end-data.start,6)<=60 or not data.title.strip():raise HTTPException(422,'Keep the trim within the source clip and between 15 and 60 seconds. A title is required.')
            candidate.update(start=data.start,end=data.end,title=data.title.strip(),caption=data.description,duration=f'{data.end-data.start:g}s')
            edit_id=secrets.token_hex(16)
            db.execute("INSERT OR REPLACE INTO clip_edits VALUES(?,?,?,?,?,'pending',NULL)",(uid,data.jobId,edit_id,device_id,json.dumps(candidate)))
            # Preserve the last verified artifact. The editing stage blocks review and publish.
            db.execute("UPDATE pipeline_jobs SET stage='editing',lease_expires=?,updated=? WHERE id=? AND user_id=?",(now+360,now,data.jobId,uid))
        return {'ok':True,'editId':edit_id,'candidate':candidate}
    @router.post('/api/worker/clip-edits/complete')
    def complete(data:CompleteEdit,request:Request):
        metadata={**data.artifact,'previewToken':data.previewToken}
        try:PublicationService.validate_artifact(metadata)
        except PublicationDenied as error:raise HTTPException(422,str(error)) from None
        if (metadata.get('width'),metadata.get('height'),metadata.get('framing'))!=(1080,1920,'blurred_fit'):raise HTTPException(422,'A captioned mobile render is required.')
        with store.connection(atomic=True) as db:
            uid,device_id=device(request,db)
            require_edit_access(db,uid)
            row=db.execute('SELECT * FROM clip_edits WHERE user_id=? AND job_id=? AND edit_id=? AND device=?',(uid,data.jobId,data.editId,device_id)).fetchone()
            if not row:raise HTTPException(409,'Edit is unavailable for this worker.')
            if row['status']=='complete':
                if json.loads(row['completed'])!=metadata:raise HTTPException(409,'Edit completion already contains a different artifact.')
                return {'ok':True}
            candidate=json.loads(row['candidate'])
            if abs(metadata['duration']-(candidate['end']-candidate['start']))>.6:raise HTTPException(422,'Rendered duration does not match the requested trim.')
            job=db.execute("SELECT 1 FROM pipeline_jobs WHERE id=? AND user_id=? AND device=? AND stage='editing' AND lease_expires>?",(data.jobId,uid,device_id,time.time())).fetchone()
            if row['status']!='pending' or not job or db.execute('SELECT 1 FROM publications WHERE user_id=? AND clip_id=?',(uid,data.jobId)).fetchone():raise HTTPException(409,'Edit was cancelled or its lease expired.')
            db.execute('UPDATE candidates SET data=? WHERE id=? AND user_id=?',(json.dumps(candidate),data.jobId,uid))
            db.execute('INSERT OR REPLACE INTO clip_artifacts VALUES(?,?,?)',(uid,data.jobId,json.dumps(metadata)))
            db.execute('INSERT OR REPLACE INTO candidate_previews VALUES(?,?,?,?,?)',(uid,data.jobId,device_id,data.previewToken,time.time()))
            db.execute("UPDATE pipeline_jobs SET stage='review',lease_expires=?,updated=? WHERE id=? AND user_id=?",(time.time()+120,time.time(),data.jobId,uid))
            db.execute("UPDATE clip_edits SET status='complete',completed=? WHERE user_id=? AND job_id=?",(json.dumps(metadata),uid,data.jobId))
        return {'ok':True}
    def abort_edit(data,request,stale=False):
        with store.connection(atomic=True) as db:
            uid,device_id=device(request,db)
            row=db.execute('SELECT * FROM clip_edits WHERE user_id=? AND job_id=? AND device=?',(uid,data.jobId,device_id)).fetchone()
            if not row or not stale and row['edit_id']!=data.editId:raise HTTPException(409,'Edit is unavailable for this worker.')
            if row['status']=='complete':raise HTTPException(409,'The edit is already complete. Reopen the updated preview.')
            clause=' AND lease_expires<=?' if stale else ''
            args=(time.time(),time.time()+120,data.jobId,uid,device_id)+((time.time(),) if stale else ())
            changed=db.execute("UPDATE pipeline_jobs SET stage='review',updated=?,lease_expires=? WHERE id=? AND user_id=? AND device=? AND stage='editing'"+clause,args)
            if changed.rowcount!=1:raise HTTPException(409,'Edit is still running or the job changed.')
            db.execute("UPDATE clip_edits SET status='aborted' WHERE user_id=? AND job_id=?",(uid,data.jobId))
        return {'ok':True}
    @router.post('/api/worker/clip-edits/abort')
    def abort(data:EditIdentity,request:Request):return abort_edit(data,request)
    @router.post('/api/worker/clip-edits/abort-stale')
    def abort_stale(data:EditJob,request:Request):return abort_edit(data,request,True)
    return router
