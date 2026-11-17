"""Authenticated scout controls and device-scoped worker metadata API."""
from fastapi import APIRouter,HTTPException,Request
from pydantic import BaseModel,ConfigDict,Field
from .scouts import ScoutStore,ScoutDenied,ScoutStartDenied
from .worker_jobs import WorkerJobs,WorkerDenied,device_user

class JobReport(BaseModel):
    model_config=ConfigDict(extra='forbid')
    jobId:str=Field(pattern=r'^[a-f0-9]{32}$')
    lease:str=Field(pattern=r'^[a-f0-9]{32}$')
    event:dict

class JobCancel(BaseModel):
    model_config=ConfigDict(extra='forbid')
    jobId:str=Field(pattern=r'^[a-f0-9]{32}$')

def build_worker_router(store,current,oauth):
    router=APIRouter();scouts=ScoutStore(store);jobs=WorkerJobs(store)
    from .discovery import Directory
    from .oauth import OAuthUnavailable
    from threading import Lock
    from collections import OrderedDict
    import time
    directory=Directory(oauth);cache=OrderedDict();cache_lock=Lock()
    from .trigger_settings import TriggerStore
    triggers=TriggerStore(store)
    def discovered(uid,platform,logins,categories):
        key=(uid,platform,tuple(logins),tuple(categories))
        with cache_lock:
            value=cache.get(key)
            if value and value[0]>time.time():return value[1]
        result=directory.streams(uid,platform,logins,categories)
        with cache_lock:
            cache[key]=(time.time()+30,result)
            while len(cache)>128:cache.popitem(last=False)
        return result
    def browse(uid,platform,logins,categories):
        try:return {'sources':directory.lookup(uid,platform,logins[0]) if len(logins)==1 else discovered(uid,platform,logins,categories)}
        except ScoutDenied as error:raise HTTPException(422,str(error))
        except OAuthUnavailable as error:raise HTTPException(409,str(error))
    def token(request):
        header=request.headers.get('authorization','')
        value=header[7:] if header.startswith('Bearer ') else ''
        with store.connection() as db:
            try:device_user(db,value)
            except WorkerDenied as error:raise HTTPException(401,str(error))
        return value
    @router.get('/api/scouts')
    def get_scouts(request:Request):
        uid=current(request)['user_id'];result=scouts.snapshot(uid);result['discoveryWarnings']={}
        twitch=oauth.vault.load(uid,'twitch')
        if twitch and 'chat:read' not in twitch['tokens'].get('scopes',[]):result['discoveryWarnings']['twitch']='Reconnect Twitch in Connect Accounts to enable read-only chat cues. Audio and speech cues remain available.'
        record=oauth.vault.load(uid,'kick')
        if record and 'channel:read' not in record['tokens'].get('scopes',[]):result['discoveryWarnings']['kick']='Reconnect Kick in Connect Accounts to grant channel access before scouting.'
        if record:
            import os
            if os.getenv('KICK_CHAT_WEBHOOK_ENABLED')!='1':result['discoveryWarnings'].setdefault('kick','Kick chat cues need service setup. Audio and speech cues remain available.')
        return result
    @router.put('/api/scouts')
    def save_scouts(selection:dict,request:Request):
        uid=current(request,True)['user_id']
        try:return scouts.save(uid,selection,allow_start=False)
        except ScoutStartDenied as error:raise HTTPException(409,str(error))
        except ScoutDenied as error:raise HTTPException(422,str(error))
    @router.put('/api/scouts/controls')
    def save_controls(values:dict,request:Request):
        try:return scouts.save_controls(current(request,True)['user_id'],values)
        except ScoutDenied as error:raise HTTPException(422,str(error))
    @router.get('/api/pipeline/jobs')
    def snapshot(request:Request):return {'jobs':jobs.snapshot(current(request)['user_id'])}
    @router.post('/api/pipeline/cancel')
    def cancel(data:JobCancel,request:Request):
        if not jobs.cancel(current(request,True)['user_id'],data.jobId):raise HTTPException(404,'Job is unavailable or cannot be cancelled.')
        return {'ok':True}
    @router.get('/api/worker/config')
    def worker_config(request:Request):
        value=token(request)
        with store.connection() as db:uid=device_user(db,value)
        result=scouts.snapshot(uid)
        result['triggers']=triggers.get(uid);result['manualTriggers']=triggers.requests(uid)
        from .analysis_api import test_enabled,customer_enabled
        import os
        result['customerAnalysisEnabled']=customer_enabled(store,uid)
        result['analysisEnabled']=test_enabled(store,os.getenv('CLIPBOT_ADMIN_USER_ID',''),uid) or result['customerAnalysisEnabled']
        result['betaAccepted']=store.beta_accepted(uid)
        with store.connection(atomic=True) as db:
            jobs.expire_captures(db,uid,time.time())
            rows=db.execute("SELECT source,stage FROM pipeline_jobs WHERE user_id=? AND stage NOT IN ('published','failed','cancelled')",(uid,)).fetchall()
        import json
        result['blockedSources']=[json.loads(r['source']) for r in rows if r['stage'] not in ('queued','capturing')]
        result['queueAvailable']=sum(r['stage'] not in ('review','ready') for r in rows)<result['effective']['slots']+2 and sum(r['stage']=='review' for r in rows)<40
        return result
    @router.get('/api/scouts/discover')
    def discover(request:Request,platform:str,logins:str='',categories:str=''):
        uid=current(request)['user_id']
        return browse(uid,platform,logins.split(',') if logins else [],categories.split(',') if categories else [])
    @router.get('/api/scouts/category-coverage')
    def category_coverage(request:Request,platform:str,categories:str=''):
        uid=current(request)['user_id']
        try:return directory.category_coverage(uid,platform,categories.split(',') if categories else [])
        except ScoutDenied as error:raise HTTPException(422,str(error))
        except OAuthUnavailable as error:raise HTTPException(409,str(error))
    @router.get('/api/scouts/categories')
    def category_search(request:Request,platform:str,query:str=''):
        uid=current(request)['user_id']
        try:return {'categories':directory.categories(uid,platform,query) if query else directory.top_categories(uid,platform)}
        except ScoutDenied as error:raise HTTPException(422,str(error))
        except OAuthUnavailable as error:raise HTTPException(409,str(error))
    @router.get('/api/worker/discovery')
    def worker_discover(request:Request):
        value=token(request)
        with store.connection() as db:uid=device_user(db,value)
        config=scouts.snapshot(uid)['effective'];sources=[];errors=[]
        if not config['running']:return {'sources':[],'errors':[]}
        for platform in ('twitch','kick'):
            if config.get('platformSlots',{}).get(platform,config['slots'])<=0:continue
            pins=list(dict.fromkeys(v['login'] for key in ('forced','favorites') for v in config[key] if v['platform']==platform))
            cats=list(dict.fromkeys(v['id'] for key in ('forcedCategories','categories') for v in config.get(key,[]) if v['platform']==platform))
            try:
                for offset in range(0,len(pins),65):sources+=discovered(uid,platform,pins[offset:offset+65],[])
                # Favorite categories reserve priority, not the entire discovery pool.
                # Legacy explicit category filters still constrain automatic selection.
                if not any(v['platform']==platform for v in config.get('categories',[])):sources+=discovered(uid,platform,[],[])
                for offset in range(0,len(cats),25):sources+=discovered(uid,platform,[],cats[offset:offset+25])
            except (OAuthUnavailable,ScoutDenied):errors.append({'platform':platform,'code':'discovery_unavailable'})
        return {'sources':sources,'errors':errors}
    @router.post('/api/worker/jobs/open')
    def open_live(source:dict,request:Request):
        value=token(request)
        with store.connection() as db:uid=device_user(db,value)
        try:
            from .scouts import source_identity
            identity=source_identity(source);config=scouts.snapshot(uid)['effective']
            found=discovered(uid,identity['platform'],[identity['login']],[])
            found=next((s for s in found if s['login']==identity['login'] and s['live']),None)
            if not found:raise WorkerDenied('This source is no longer live.')
            pinned=identity in config['forced'] or identity in config['favorites']
            allowed={(c['platform'],c['id']) for c in config['categories']}
            pinned=pinned or (identity['platform'],found['categoryId']) in {(c['platform'],c['id']) for c in config.get('forcedCategories',[])}
            if allowed and not pinned and (identity['platform'],found['categoryId']) not in allowed:raise WorkerDenied('This source is outside your selected categories.')
            return {'job':jobs.open(value,identity)}
        except ScoutDenied as error:raise HTTPException(422,str(error))
        except (WorkerDenied,OAuthUnavailable) as error:raise HTTPException(409,str(error))
    @router.post('/api/worker/jobs/resume')
    def resume(data:JobCancel,request:Request):
        try:return {'job':jobs.resume(token(request),data.jobId)}
        except WorkerDenied as error:raise HTTPException(409,str(error))
    @router.post('/api/worker/jobs/claim')
    def claim(request:Request):
        try:return {'job':jobs.claim(token(request))}
        except WorkerDenied as error:raise HTTPException(401,str(error))
    @router.post('/api/worker/jobs/report')
    def report(data:JobReport,request:Request):
        value=token(request)
        try:return jobs.report(value,data.jobId,data.lease,data.event)
        except WorkerDenied as error:raise HTTPException(409,str(error))
    return router,scouts,jobs
