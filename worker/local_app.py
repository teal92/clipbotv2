"""Loopback-only worker setup and capability-scoped local media preview."""
import argparse,hashlib,html,hmac,ipaddress,json,re,secrets,threading,time,webbrowser
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI,Request,HTTPException
from fastapi.responses import HTMLResponse,JSONResponse,Response,FileResponse
from pydantic import BaseModel,ConfigDict,Field
from .client import WorkerClient,service_origin,DEFAULT_ORIGIN,configured_origin
from .prerequisites import prerequisites

from .setup_page import SETUP_JS,setup_html
from .version import VERSION

class PairDevice(BaseModel):
    model_config=ConfigDict(extra='forbid')
    code:str=Field(min_length=20,max_length=100)
    hardwareSlots:int=Field(default=2,ge=1,le=40,strict=True)

class LocalFeedback(BaseModel):
    model_config=ConfigDict(extra='forbid')
    candidateId:str=Field(pattern=r'^[a-f0-9]{32}$')
    userId:str=Field(pattern=r'^[a-f0-9]{32}$')
    decision:str=Field(pattern=r'^(approve|reject)$')
    reasons:list[str]=Field(max_length=10)
    justification:str=Field(default='',max_length=1000)

class FeedbackReceipt(BaseModel):
    model_config=ConfigDict(extra='forbid')
    receipt:dict

def create_local_app(origin=DEFAULT_ORIGIN,root=None,start_runtime=True):
    origin=service_origin(origin);root=Path(root or Path(__file__).parent/'data'/'jobs').resolve();root.mkdir(parents=True,exist_ok=True)
    secret=secrets.token_hex(32);client=WorkerClient(origin);stop=threading.Event();lifecycle=threading.Lock()
    model_directory=Path(__file__).parent/'data'/'models'/'base'
    state={'client':client,'runtime':None,'processor':None,'thread':None,'message':'Generate a pairing code in ClipBot → Connect Accounts, then enter it here.','slots':2}
    previews={};credential_path=root.parent/'device.bin';verified_account=None;feedback_lock=threading.Lock()
    def halt():
        runtime=state['runtime'];processor=state['processor']
        if runtime:runtime.close()
        if processor:processor.close()
        state['runtime']=None;state['processor']=None;state['controller']=None;previews.clear()
    def loop():
        delay=1
        while not stop.wait(delay):
            controller=state.get('controller')
            if not controller:continue
            delay=controller.tick();state['message']=controller.message
            if delay is None:stop.set();halt();return
    def start_loop(controller):
        state['controller']=controller;stop.clear();state['thread']=threading.Thread(target=loop,daemon=True);state['thread'].start()
    def health_only():
        from .lifecycle import CompanionHealth
        controller=CompanionHealth(state['client'],state['slots']);state['message']=controller.message;start_loop(controller);return False
    def begin():
        if not start_runtime:return True
        ready=prerequisites(model_directory)
        if not all(ready.values()):return health_only()
        from .processor import ClipProcessor
        from .runtime import MonitorRuntime
        from .lifecycle import CompanionLifecycle
        try:processor=ClipProcessor(state['client'],root,model_directory,previews)
        except Exception:return health_only()
        runtime=MonitorRuntime(state['client'],root,processor.submit,hardware_slots=state['slots'])
        state['runtime']=runtime;state['processor']=processor
        start_loop(CompanionLifecycle(runtime,processor,state['client']));return True
    @asynccontextmanager
    async def lifespan(app):
        if start_runtime:
            from .credentials import load
            with lifecycle:
                try:token=load(credential_path,origin)
                except RuntimeError:
                    token=None;state['message']='Unlock your login keychain or desktop keyring, then reconnect the companion.'
                if token:
                    client.token=token
                    try:client.heartbeat()
                    except Exception:pass # Only WorkerClient's revoked 401 clears pairing.
                    if client.token:
                        try:begin()
                        except Exception:state['message']='Companion could not initialize local processing. Reinstall or reconnect.'
        yield
        stop.set();halt();state['client'].close()
    app=FastAPI(docs_url=None,redoc_url=None,openapi_url=None,lifespan=lifespan);app.state.previews=previews;app.state.worker=state
    from server.body_limit import RequestBodyLimit
    class LocalBodyLimit(RequestBodyLimit):
        async def __call__(self,scope,receive,send):
            # Dynamic capability paths have a separate bounded JSON allowance.
            bounded=RequestBodyLimit(self.app,max_bytes=8192 if scope.get('path','').startswith('/feedback/') else 2048,limits={})
            await bounded(scope,receive,send)
    app.add_middleware(LocalBodyLimit,max_bytes=2048,limits={})
    @app.middleware('http')
    async def protect(request,call_next):
        if request.headers.get('host') not in ('127.0.0.1:8767','localhost:8767'):return JSONResponse({'detail':'Local worker access only.'},status_code=403)
        try:loopback=ipaddress.ip_address(request.client.host).is_loopback if request.client else False
        except ValueError:loopback=False
        if not loopback:return JSONResponse({'detail':'Local worker access only.'},status_code=403)
        feedback=request.url.path.startswith('/feedback/')
        if feedback:
            if request.headers.get('origin')!=origin:return JSONResponse({'detail':'Open feedback from your paired ClipBot service.'},status_code=403)
            if request.method=='OPTIONS':
                if request.headers.get('access-control-request-method') not in ('POST','GET') or request.headers.get('access-control-request-headers','').lower() not in ('','content-type'):return JSONResponse({'detail':'Invalid feedback preflight.'},status_code=403)
                return Response(status_code=204,headers={'Access-Control-Allow-Origin':origin,'Access-Control-Allow-Methods':'GET, POST','Access-Control-Allow-Headers':'Content-Type','Vary':'Origin','Cache-Control':'no-store'})
        if request.method=='POST' and not feedback:
            if request.headers.get('origin') not in ('http://127.0.0.1:8767','http://localhost:8767') or not hmac.compare_digest(request.headers.get('x-csrf-token',''),secret):return JSONResponse({'detail':'Reload this local setup page.'},status_code=403)
            length=request.headers.get('content-length','0')
            if not length.isdigit() or int(length)>2048:return JSONResponse({'detail':'Request too large.'},status_code=413)
        response=await call_next(request);response.headers.update({'Cache-Control':'no-store','X-Content-Type-Options':'nosniff','Referrer-Policy':'no-referrer','X-Frame-Options':'DENY','Content-Security-Policy':"default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; media-src 'self'; frame-ancestors 'none'; form-action 'self'"})
        if feedback:response.headers.update({'Access-Control-Allow-Origin':origin,'Vary':'Origin'})
        return response
    @app.get('/')
    def setup():return HTMLResponse(setup_html(origin,secret))
    @app.get('/setup.js')
    def javascript():return Response(SETUP_JS,media_type='application/javascript')
    @app.get('/status')
    def status():
        runtime=state['runtime']
        return {'version':VERSION,'paired':bool(state['client'].token),'message':state['message'],'metrics':runtime.metrics() if runtime else None,'trayVisible':bool(getattr(getattr(app.state,'tray_icon',None),'visible',False)),'tools':prerequisites(model_directory)}
    @app.post('/pair')
    def pair(data:PairDevice):
        with lifecycle:
            stop.set()
            thread=state['thread']
            if thread:
                thread.join(timeout=60)
                if thread.is_alive():raise HTTPException(409,'The previous worker is still stopping. Wait a moment before pairing again.')
            halt();state['client'].close();state['client']=WorkerClient(origin)
            try:
                state['client'].connect(data.code);state['client'].heartbeat();state['slots']=data.hardwareSlots
                from .credentials import save
                try:save(credential_path,origin,state['client'].token)
                except RuntimeError:
                    state['client'].token=None;state['client'].close()
                    state['message']='Secure pairing could not be saved. Unlock your login keychain or desktop keyring and try again.'
                    raise HTTPException(409,state['message']) from None
                if begin():state['message']='Paired. Use Start ClipBot on the website.'
                return {'message':state['message']}
            except HTTPException:raise
            except Exception:
                state['client'].token=None;state['client'].close()
                raise HTTPException(409,'Pairing did not finish. Generate a new code in ClipBot.') from None
    app.state.pair_companion=lambda code:pair(PairDevice(code=code,hardwareSlots=state['slots']))
    def clip(token):
        path=previews.get(token)
        if path:path=path.resolve()
        allowed=bool(path and (path.name in ('clip.mp4','candidate-preview.mp4') or re.fullmatch(r'clip-edit-[a-f0-9]{32}\.mp4',path.name)))
        if not path or not path.is_file() or not allowed or path.parent.parent!=root:raise HTTPException(404,'Preview is unavailable on this computer.')
        return path
    def checked_feedback_memory(token,user_id=None,refresh=True):
        nonlocal verified_account
        from .personal_memory import PersonalMemory
        if not re.fullmatch(r'[a-f0-9]{64}',token):raise HTTPException(404,'Feedback preview is unavailable.')
        path=clip(token).resolve();candidate_id=path.parent.name
        if path.parent.parent!=root or not re.fullmatch(r'[a-f0-9]{32}',candidate_id):raise HTTPException(404,'Feedback preview is unavailable.')
        paired=state['client']
        if not paired.token:raise HTTPException(403,'Pair this worker before saving feedback.')
        fingerprint=hashlib.sha256(paired.token.encode()).hexdigest()
        cached_read=refresh=='cached'
        if cached_read:
            refresh=not (verified_account and verified_account[1]==fingerprint and time.monotonic()-verified_account[2]<=90)
        if refresh:
            try:remote=paired.request('GET','/api/worker/state')
            except Exception:raise HTTPException(409,'Account verification unavailable; feedback was not saved.') from None
            uid=remote.get('userId')
            if not isinstance(uid,str) or not re.fullmatch(r'[a-f0-9]{32}',uid):raise HTTPException(409,'Update ClipBot before saving local feedback.')
            owned=frozenset(j.get('id') for j in remote.get('jobs',[]) if isinstance(j,dict) and isinstance(j.get('id'),str))
            if candidate_id not in owned:
                # Historical feedback need not expand the frequently polled job snapshot.
                try:proof=paired.request('GET','/api/worker/feedback-owner?candidateId='+candidate_id)
                except Exception:raise HTTPException(403,'Candidate is not owned by the paired account.') from None
                if not isinstance(proof,dict) or proof.get('userId')!=uid or proof.get('candidateId')!=candidate_id:raise HTTPException(403,'Candidate is not owned by the paired account.')
                owned=owned|{candidate_id}
            verified_account=(uid,fingerprint,time.monotonic(),owned)
        if not verified_account or verified_account[1]!=fingerprint or time.monotonic()-verified_account[2]>90:raise HTTPException(409,'Account verification expired. Save the feedback again.')
        if cached_read and candidate_id not in verified_account[3]:
            try:proof=paired.request('GET','/api/worker/feedback-owner?candidateId='+candidate_id)
            except Exception:raise HTTPException(403,'Candidate is not owned by the paired account.') from None
            if not isinstance(proof,dict) or proof.get('userId')!=verified_account[0] or proof.get('candidateId')!=candidate_id:raise HTTPException(403,'Candidate is not owned by the paired account.')
            verified_account=(*verified_account[:3],verified_account[3]|{candidate_id})
        if candidate_id not in verified_account[3]:raise HTTPException(403,'Candidate is not owned by the paired account.')
        uid=verified_account[0]
        if user_id is not None and user_id!=uid:raise HTTPException(403,'Feedback belongs to another account.')
        return PersonalMemory(root.parent/'personal-memory',origin,uid),candidate_id,uid
    def feedback_memory(token,user_id=None,refresh=True):
        # Serialize cache refreshes so concurrent browser hydration verifies once.
        with feedback_lock:return checked_feedback_memory(token,user_id,refresh)
    @app.post('/feedback/{token}')
    def local_feedback(token:str,data:LocalFeedback):
        memory,candidate_id,uid=feedback_memory(token,data.userId)
        if data.candidateId!=candidate_id:raise HTTPException(403,'Feedback candidate does not match this preview.')
        try:memory.record(candidate_id,data.decision,data.reasons,data.justification)
        except ValueError as error:raise HTTPException(422,str(error)) from None
        return {'ok':True,'memorySummary':memory.summary()}
    @app.get('/feedback/{token}')
    def read_feedback(token:str):
        memory,candidate_id,uid=feedback_memory(token,refresh='cached')
        value=memory.review(candidate_id)
        return {'feedback':{'candidateId':candidate_id,'userId':uid,**value} if value else None}
    @app.post('/feedback/{token}/confirm')
    def confirm_feedback(token:str,data:FeedbackReceipt):
        receipt=data.receipt
        if set(receipt)!={'candidateId','userId','decision','issuedAt','signature'}:raise HTTPException(422,'Invalid feedback receipt.')
        memory,candidate_id,uid=feedback_memory(token,receipt.get('userId'),refresh=False)
        payload={k:v for k,v in receipt.items() if k!='signature'};issued=payload.get('issuedAt')
        if type(issued) is not int or not time.time()-120<=issued<=time.time()+10 or payload.get('candidateId')!=candidate_id or payload.get('decision') not in ('approve','reject'):raise HTTPException(403,'Feedback receipt is invalid or expired.')
        signature=receipt.get('signature');key=hashlib.sha256(state['client'].token.encode()).digest()
        expected=hmac.new(key,json.dumps(payload,sort_keys=True,separators=(',',':')).encode(),hashlib.sha256).hexdigest()
        if not isinstance(signature,str) or not hmac.compare_digest(signature,expected):raise HTTPException(403,'Feedback receipt is not authenticated.')
        pending=memory.review(candidate_id)
        if not pending or pending['decision']!=payload['decision']:raise HTTPException(409,'Feedback changed after this approval. Save the current decision again.')
        memory.confirm([payload]);return {'ok':True,'memorySummary':memory.summary()}
    from .clip_edit import LocalClipEdit
    @app.post('/feedback/{token}/edit')
    def start_clip_edit(token:str,data:LocalClipEdit):
        _,candidate_id,_=feedback_memory(token,data.userId)
        processor=state.get('processor')
        if not processor:raise HTTPException(409,'The companion is not ready for editing.')
        try:return processor.start_edit(candidate_id,token,data.model_dump(exclude={'userId'}))
        except Exception:raise HTTPException(409,'Could not start edits. Reopen the undecided clip with the updated companion.') from None
    @app.get('/feedback/{token}/edit')
    def clip_edit_status(token:str):
        _,candidate_id,_=feedback_memory(token,refresh='cached')
        processor=state.get('processor');entry=processor.entries.get(candidate_id) if processor else None
        if not entry:raise HTTPException(409,'Clip editing is unavailable.')
        return {'ok':True,**entry.get('edit_status',{'status':'idle'})}
    @app.get('/preview/{token}')
    def preview(token:str):
        clip(token)
        return HTMLResponse(f"<!doctype html><meta name=viewport content='width=device-width,initial-scale=1'><title>ClipBot Preview</title><body style='background:#090d12;color:white;font:16px system-ui;text-align:center'><h1>Local clip preview</h1><video controls style='height:80vh;max-width:100%' src='/media/{html.escape(token)}'></video><p>Return to ClipBot to approve or reject the candidate, or review a finished clip for publishing.</p></body>")
    @app.get('/media/{token}')
    def media(token:str):return FileResponse(clip(token),media_type='video/mp4')
    return app

def main():
    parser=argparse.ArgumentParser(description='ClipBot local worker and preview');parser.add_argument('--service',default=configured_origin());parser.add_argument('--no-browser',action='store_true');args=parser.parse_args()
    import uvicorn
    if not args.no_browser:threading.Timer(1,lambda:webbrowser.open('http://127.0.0.1:8767')).start()
    uvicorn.run(create_local_app(args.service),host='127.0.0.1',port=8767,access_log=False,proxy_headers=False)
if __name__=='__main__':main()
