from .client_ip import client_ip
import json
"""Single-instance pre-launch API. Public signup and paid AI remain closed."""
import hmac,os,re,sqlite3,ipaddress,logging,time,hashlib
from pathlib import Path
from decimal import Decimal,InvalidOperation
from fastapi import FastAPI,Request,HTTPException
from fastapi.responses import JSONResponse,RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.concurrency import run_in_threadpool
from pydantic import BaseModel,Field,ConfigDict,StrictInt,StrictBool
from .store import Store
from .admin import BETA_VERSION
from .connections import connection_status,PLATFORMS
from .oauth import OAuthService,OAuthUnavailable
from .oauth_store import OAuthInvalid
from .pricing import quote
from .billing import Billing,BillingUnavailable
from .network_check import log_billing_failure
import stripe
from .budgets import BudgetLedger
from .body_limit import RequestBodyLimit
from .davey_api import DaveyChange
from fastapi.exceptions import RequestValidationError

ROOT=Path(__file__).resolve().parents[1]
class ConnectionStart(BaseModel):
    model_config=ConfigDict(extra='forbid')
    accountType:str=Field(max_length=20)

class DestinationChoice(BaseModel):
    model_config=ConfigDict(extra='forbid')
    destinationId:str=Field(min_length=1,max_length=150)

class BetaAcceptance(BaseModel):
    model_config=ConfigDict(extra='forbid')
    version:str=Field(max_length=50)

class Credentials(BaseModel):
    model_config=ConfigDict(extra='forbid')
    email:str=Field(min_length=3,max_length=254)
    password:str=Field(min_length=12,max_length=128)
    name:str=Field(default='',max_length=80)
class SignupCredentials(Credentials):
    termsVersion:str|None=Field(default=None,max_length=50)

class Preferences(BaseModel):
    model_config=ConfigDict(extra='forbid')
    usagePreset:str
    focus:str
    avoid:str
    approval:str='review'
    progression:DaveyChange|None=None

class Review(BaseModel):
    model_config=ConfigDict(extra='forbid')
    candidate_id:str=Field(min_length=1,max_length=150)
    decision:str=Field(max_length=10)
    reasons:list[str]=Field(default_factory=list,max_length=10)
    justification:str=Field(default='',max_length=1000)
    localLearning:StrictBool=False

class CheckoutRequest(BaseModel):
    model_config=ConfigDict(extra='forbid')
    plan:str=Field(max_length=20)
    custom:dict[str,StrictInt]|None=None
    quotedMonthlyCents:StrictInt|None=None

class PairingCode(BaseModel):
    model_config=ConfigDict(extra='forbid')
    code:str=Field(min_length=20,max_length=100)

class QuoteRequest(BaseModel):
    model_config=ConfigDict(extra='forbid')
    plan:str=Field(max_length=20)
    custom:dict[str,StrictInt]|None=None

class SupportReport(BaseModel):
    model_config=ConfigDict(extra='forbid')
    kind:str=Field(max_length=20)
    area:str=Field(max_length=30)
    title:str=Field(min_length=5,max_length=120)
    details:str=Field(min_length=20,max_length=4000)
    steps:str=Field(default='',max_length=2000)
    expected:str=Field(default='',max_length=1000)
    frequency:str=Field(default='unsure',max_length=20)
    impact:str=Field(default='minor',max_length=20)
    environment:str=Field(default='',max_length=300)

def create_app(store=None,origin=None,local_signup=None,billing=None,oauth=None):
    origin=(origin or os.getenv('CLIPBOT_ORIGIN','http://127.0.0.1:8766')).rstrip('/')
    if local_signup is None:local_signup=os.getenv('CLIPBOT_LOCAL_SIGNUP')=='1' and origin in ('http://127.0.0.1:8766','http://localhost:8766')
    store=store or Store(Path(os.getenv('CLIPBOT_DB_PATH',str(ROOT/'server'/'data'/'clipbot.db'))))
    def owner_limit(name,default):
        try:
            value=Decimal(os.getenv(name,str(default)))
            if not value.is_finite() or value<0 or value>10000:raise ValueError('Invalid owner spending limit')
            return int(value*1000000)
        except (InvalidOperation,ValueError):raise RuntimeError('Invalid owner spending limit; server refused to start')
    ledger=BudgetLedger(store,global_monthly=owner_limit('CLIPBOT_GLOBAL_MONTHLY_USD',400),global_daily=owner_limit('CLIPBOT_GLOBAL_DAILY_USD',20)) # Dispatch stays off.
    from contextlib import asynccontextmanager
    @asynccontextmanager
    async def lifespan(application):
        if hasattr(application.state,'edge_guard'):application.state.edge_guard.reopen()
        application.state.chat_relay.start()
        application.state.report_delivery.start()
        try:yield
        finally:
            application.state.report_delivery.stop()
            application.state.chat_relay.close()
            if hasattr(application.state,'edge_guard'):application.state.edge_guard.close()
    app=FastAPI(docs_url=None,redoc_url=None,openapi_url=None,lifespan=lifespan)
    admin_uid=os.getenv('CLIPBOT_ADMIN_USER_ID','').strip()
    if admin_uid and not re.fullmatch(r'[a-f0-9]{32}',admin_uid):raise RuntimeError('Invalid owner account configuration')
    from .customer_access import CustomerAccess,build_customer_access_router
    access=CustomerAccess(store,origin)
    app.state.customer_access=access
    billing=billing or Billing(store,origin)
    oauth=oauth or OAuthService(store,origin)
    app.state.oauth=oauth
    app.state.store=store;app.state.ledger=ledger;app.state.billing=billing
    from .visitor_api import visitor_router
    visitors_router,app.state.site_visitors=visitor_router(store)
    app.include_router(visitors_router)
    from .telemetry import Telemetry
    telemetry=Telemetry();app.state.telemetry=telemetry
    from .report_delivery import ReportDelivery,ReportRejected
    report_delivery=ReportDelivery(store);app.state.report_delivery=report_delivery
    from .edge_protection import EdgeProtection,verified_principal
    from .site_availability import SiteAvailability,SiteAvailabilityMiddleware
    availability=SiteAvailability(store);app.state.site_availability=availability
    app.add_middleware(SiteAvailabilityMiddleware,control=availability)
    app.add_middleware(EdgeProtection,principal=verified_principal(store),persistent_path=store.path.parent/'request-limits.sqlite',register=lambda guard:setattr(app.state,'edge_guard',guard))
    app.add_middleware(RequestBodyLimit)
    @app.exception_handler(RequestValidationError)
    async def invalid_request(request,error):
        return JSONResponse({'detail':'Check your entries and choose the listed options.'},status_code=422)
    @app.middleware('http')
    async def security(request,call_next):
        if request.method in ('POST','PUT','PATCH','DELETE'):
            webhook=request.url.path in ('/api/billing/webhook','/api/events/kick/chat') and request.method=='POST'
            if not webhook and request.headers.get('origin')!=origin:return JSONResponse({'detail':'Reload ClipBot and try again.'},status_code=403)
            length=request.headers.get('content-length','0')
            if not length.isdigit() or int(length)>(131072 if webhook else 65536 if request.url.path=='/api/worker/analyze' else 262144 if request.url.path=='/api/worker/companion-heartbeat' else 196608 if request.url.path=='/api/account/avatar' else 16384):return JSONResponse({'detail':'Request too large.'},status_code=413)
        started=time.monotonic()
        response=await call_next(request)
        if request.url.path.startswith('/api/'):telemetry.record((time.monotonic()-started)*1000,response.status_code)
        response.headers['Cache-Control']='no-store'
        response.headers['X-Content-Type-Options']='nosniff'
        response.headers['Referrer-Policy']='no-referrer' if request.url.path.endswith('/callback') else 'same-origin'
        response.headers['X-Frame-Options']='DENY'
        response.headers['Content-Security-Policy']="default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; media-src 'self' http://127.0.0.1:8767; img-src 'self' data: https://static-cdn.jtvnw.net https://images.kick.com; connect-src 'self' http://127.0.0.1:8767; frame-src https://player.twitch.tv https://player.kick.com; frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
        if origin.startswith('https://'):response.headers['Strict-Transport-Security']='max-age=31536000'
        return response
    def current(request,write=False):
        session=store.session(request.cookies.get('clipbot_session',''))
        if not session:raise HTTPException(401,'Sign in to continue.')
        if write and not hmac.compare_digest(request.headers.get('x-csrf-token',''),session['csrf']):raise HTTPException(403,'Reload ClipBot and try again.')
        return session
    def account(session):
        coverage=store.coverage(session['user_id'])
        return {'isAdmin':bool(admin_uid and hmac.compare_digest(session['user_id'],admin_uid) and store.user(session['user_id'])['email']!='clipbot-local-development@example.invalid'),'user':store.user(session['user_id']),'csrfToken':session['csrf'],'readiness':access.readiness(session['user_id']),'plan':{'active':bool(coverage),'name':('Custom · Owner showcase' if coverage and coverage.get('ownerShowcase') else ((store.billing_status(session['user_id']) or {}).get('plan','Paid coverage').title()) if coverage else 'No active plan'),'coverage':coverage},'billing':{'connected':billing.ready,'customAvailable':billing.ready and bool(billing.custom_product and billing.custom_prices),'mode':billing.mode,'sandbox':not billing.live,'cancellation':billing.cancellation_status(session['user_id']),'portalAvailable':billing.ready and bool(billing.portal_configuration),'subscription':store.billing_status(session['user_id']),'change':billing.change_status(session['user_id']),'message':('Stripe test billing is connected. Test payments only; no real charges.' if not billing.live else 'Stripe live billing is connected.') if billing.ready else 'Billing is not connected. No payment method is stored.'}}
    def authenticate_response(uid,status=200):
        token,csrf=store.new_session(uid)
        response=JSONResponse(account({'user_id':uid,'csrf':csrf}),status_code=status)
        response.set_cookie('clipbot_session',token,max_age=86400,httponly=True,secure=origin.startswith('https://'),samesite='strict',path='/')
        return response
    def rate(request):
        if not store.auth_rate(client_ip(request)):raise HTTPException(429,'Too many attempts. Try again in 15 minutes.')
    def local_bypass_allowed(request):
        try:peer_local=ipaddress.ip_address(request.client.host).is_loopback if request.client else False
        except ValueError:peer_local=False
        return os.getenv('CLIPBOT_DEV_BYPASS')=='1' and local_signup and origin in ('http://127.0.0.1:8766','http://localhost:8766') and peer_local
    @app.get('/api/auth/options')
    def auth_options(request:Request):return {'developmentBypass':bool(local_bypass_allowed(request))}
    @app.post('/api/auth/dev-bypass')
    def dev_bypass(request:Request):
        if not local_bypass_allowed(request):raise HTTPException(403,'Development bypass is available only on the local development server.')
        rate(request)
        return authenticate_response(store.development_user())
    @app.post('/api/auth/signup')
    def signup(data:SignupCredentials,request:Request):
        rate(request)
        try:loopback=ipaddress.ip_address(request.client.host).is_loopback if request.client else False
        except ValueError:loopback=False
        if access.signup_enabled:
            if not access.signup_allowed(data.email):raise HTTPException(503,'Public registration opens after launch checks are complete.')
            if not access.public_signup_ready():raise HTTPException(503,'Registration requires working verification email and verified edge protection.')
            if os.getenv('RENDER')=='true':
                try:verified_peer=ipaddress.ip_address(client_ip(request)).is_global
                except ValueError:verified_peer=False
                if not verified_peer:raise HTTPException(503,'Registration is paused while ingress protection is verified.')
        elif not local_signup or not loopback:raise HTTPException(503,'Public registration opens after launch checks are complete.')
        from .legal import POLICY_VERSION
        if data.termsVersion!=POLICY_VERSION:raise HTTPException(422,'Accept the current Terms and acknowledge the Privacy Policy before signing up.')
        from .password_policy import validate_new_password
        from .store import normalize_username
        try:
            validate_new_password(data.password);username=normalize_username(data.name)
        except ValueError as error:raise HTTPException(422,str(error)) from None
        email=data.email.strip().lower()
        if email=='clipbot-local-development@example.invalid':raise HTTPException(422,'This address is reserved for local development.')
        if not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+',email):raise HTTPException(422,'Enter a valid email address.')
        try:uid=store.create_user(email,data.password,username,terms_version=data.termsVersion,signup_username=True)
        except sqlite3.IntegrityError:raise HTTPException(409,'Email or username is unavailable. Try a different username or sign in.')
        response=authenticate_response(uid,201)
        if access.signup_enabled:
            from starlette.background import BackgroundTask
            response.background=BackgroundTask(access.request_verification,uid,client_ip(request))
        return response
    @app.post('/api/auth/login')
    def login(data:Credentials,request:Request):
        rate(request)
        email=data.email.strip().lower()
        if not store.auth_rate('account:'+hashlib.sha256(email.encode()).hexdigest()):raise HTTPException(429,'Too many attempts. Try again in 15 minutes.')
        uid=store.authenticate(email,data.password)
        if not uid:raise HTTPException(401,'Email or password is incorrect.')
        return authenticate_response(uid)
    @app.post('/api/auth/logout')
    def logout(request:Request):
        current(request,True);store.logout(request.cookies.get('clipbot_session',''))
        response=JSONResponse({'ok':True});response.delete_cookie('clipbot_session',path='/');return response
    @app.get('/api/account')
    def get_account(request:Request):return account(current(request))
    @app.post('/api/presence')
    def presence(request:Request):
        store.record_presence(current(request,True));return {'ok':True}
    @app.post('/api/beta/accept')
    def accept_beta(data:BetaAcceptance,request:Request):
        uid=current(request,True)['user_id']
        if data.version!=BETA_VERSION:raise HTTPException(422,'Reload and read the current beta feedback notice.')
        store.accept_beta(uid);return {'ok':True,'version':BETA_VERSION}
    @app.get('/api/connections')
    def connections(request:Request):return connection_status(store,current(request)['user_id'],oauth)
    @app.post('/api/connections/{platform}/start')
    def start_connection(platform:str,data:ConnectionStart,request:Request):
        session=current(request,True)
        if platform not in {entry[0] for entry in PLATFORMS}:raise HTTPException(404,'Platform not supported.')
        if data.accountType not in ('personal','professional','developer'):raise HTTPException(422,'Choose a listed account type.')
        try:url,cookie=oauth.start(session,platform)
        except (OAuthUnavailable,OAuthInvalid) as error:raise HTTPException(503,str(error)) from None
        response=JSONResponse({'authorizationUrl':url})
        response.set_cookie('clipbot_oauth_'+platform,cookie,max_age=600,httponly=True,secure=True,samesite='lax',path=f'/api/connections/{platform}/callback')
        return response
    @app.get('/api/connections/{platform}/callback')
    def connection_callback(platform:str,request:Request):
        if platform not in {entry[0] for entry in PLATFORMS}:raise HTTPException(404,'Platform not supported.')
        result='failed'
        try:
            query=request.query_params
            if any(len(query.getlist(name))>1 for name in ('state','code','error')):raise OAuthInvalid('Start again.')
            session=store.session(request.cookies.get('clipbot_session',''))
            uid,profile=oauth.callback(platform,query.get('state',''),request.cookies.get('clipbot_oauth_'+platform,''),query.get('code',''),query.get('error',''),session['user_id'] if session else None)
            result='choose_destination' if profile.get('destinationSelected') is False else 'connected'
        except (OAuthUnavailable,OAuthInvalid,KeyError,TypeError,ValueError) as error:
            reason=str(error) if isinstance(error,(OAuthUnavailable,OAuthInvalid)) else 'Invalid platform response format.'
            logging.getLogger('clipbot.oauth').warning('Account authorization did not finish: platform=%s reason=%s',platform,reason)
        response=RedirectResponse('/?view=connections&platform='+platform+'&result='+result,status_code=303)
        response.delete_cookie('clipbot_oauth_'+platform,path=f'/api/connections/{platform}/callback',secure=True,httponly=True,samesite='lax')
        response.headers['Referrer-Policy']='no-referrer'
        return response
    @app.get('/api/connections/{platform}/destinations')
    def connection_destinations(platform:str,request:Request):
        uid=current(request)['user_id']
        if platform not in ('instagram','facebook'):raise HTTPException(404,'Destination selection is not required.')
        try:return {'destinations':oauth.destinations(uid,platform)}
        except OAuthInvalid:raise HTTPException(409,'Reconnect this account.') from None
    @app.post('/api/connections/{platform}/destination')
    def select_connection_destination(platform:str,data:DestinationChoice,request:Request):
        uid=current(request,True)['user_id']
        if platform not in ('instagram','facebook'):raise HTTPException(404,'Destination selection is not required.')
        try:oauth.select(uid,platform,data.destinationId)
        except OAuthInvalid as error:raise HTTPException(409,str(error)) from None
        return {'ok':True}
    @app.post('/api/connections/{platform}/disconnect')
    def disconnect_connection(platform:str,request:Request):
        uid=current(request,True)['user_id']
        if platform not in {entry[0] for entry in PLATFORMS}:raise HTTPException(404,'Platform not supported.')
        try:revoked=oauth.disconnect(uid,platform)
        except (OAuthInvalid,OAuthUnavailable):
            oauth.vault.disconnect(uid,platform);revoked=False
        return {'ok':True,'message':'Disconnected from ClipBot.' if revoked else 'Disconnected from ClipBot. You can also remove ClipBot access in the platform account settings.'}
    @app.post('/api/connections/{platform}/refresh')
    def refresh_connection(platform:str,request:Request):
        uid=current(request,True)['user_id']
        if platform not in {entry[0] for entry in PLATFORMS}:raise HTTPException(404,'Platform not supported.')
        try:oauth.refresh(uid,platform)
        except (OAuthInvalid,OAuthUnavailable) as error:raise HTTPException(409,str(error)) from None
        return {'ok':True}

    @app.get('/api/workspace')
    def workspace(request:Request):
        uid=current(request)['user_id']
        candidates,reviews,count=store.workspace_feedback(uid)
        from .display_text import display_text
        for item in candidates:
            for key in ('title','caption','rationale'):item[key]=display_text(item.get(key,''))
        pipeline=app.state.pipeline_jobs.snapshot(uid)
        selection_context=store.davey.context_key(uid)
        with store.connection() as db:
            for candidate in candidates:
                run=db.execute('SELECT personal_context_used FROM analysis_runs WHERE user_id=? AND job_id=?',(uid,candidate['id'])).fetchone()
                candidate['personalContextUsed']=bool(run and run[0])
                prediction=db.execute('SELECT decision FROM davey_predictions WHERE user_id=? AND job_id=? AND context_key=? AND invalidated=0',(uid,candidate['id'],selection_context)).fetchone()
                if prediction:candidate['daveyPrediction']=prediction[0]
                preview=db.execute('SELECT p.token FROM candidate_previews p JOIN worker_devices d ON d.token=p.device WHERE p.user_id=? AND p.job_id=? AND d.user_id=? AND d.expires>?',(uid,candidate['id'],uid,__import__('time').time())).fetchone()
                if preview:
                    candidate['previewUrl']='http://127.0.0.1:8767/preview/'+preview['token']
                    artifact=db.execute('SELECT data FROM clip_artifacts WHERE user_id=? AND clip_id=?',(uid,candidate['id'])).fetchone()
                    if artifact:candidate['previewFormat']=json.loads(artifact['data']).get('framing')
            ready=[]
            for r in db.execute("SELECT a.clip_id,a.data,c.data candidate FROM clip_artifacts a JOIN pipeline_jobs j ON j.id=a.clip_id AND j.user_id=a.user_id LEFT JOIN candidates c ON c.id=a.clip_id AND c.user_id=a.user_id WHERE a.user_id=? AND j.stage IN ('ready','publishing','published') ORDER BY j.updated DESC LIMIT 100",(uid,)):
                artifact=json.loads(r['data']);candidate=json.loads(r['candidate']) if r['candidate'] else {}
                for key in ('title','caption','rationale'):candidate[key]=display_text(candidate.get(key,''))
                ready.append({**candidate,'id':r['clip_id'],'artifact':{k:v for k,v in artifact.items() if k!='previewToken'},'previewUrl':'http://127.0.0.1:8767/preview/'+artifact.get('previewToken','')})
        return {'preferences':store.get_preferences(uid),'davey':app.state.davey.status(uid),'sources':[row['source'] for row in pipeline if row['stage']=='capturing' and row['updated']>__import__('time').time()-90],'scouts':{**app.state.scouts.snapshot(uid),'companion':app.state.companion.status(uid)},'candidates':candidates,'reviews':reviews,'processing':[row for row in pipeline if row['stage'] not in ('published','failed','cancelled','ready')],'pipelineJobs':pipeline,'ready':ready,'publications':app.state.publication.snapshot(uid),'published':[p for p in app.state.publication.snapshot(uid) if p['status']=='published'],'feedbackCount':count,'betaFeedback':{'required':True,'accepted':store.beta_accepted(uid),'version':BETA_VERSION},'workerConnected':store.worker_connected(uid),'aiConfigured':False}
    @app.put('/api/davey')
    def davey(data:Preferences,request:Request):
        uid=current(request,True)['user_id']
        if data.usagePreset not in ('paused','light','balanced','busy') or data.focus not in ('balanced','humor','gameplay','reactions') or data.avoid not in ('personal','sensitive','all') or data.approval!='review':raise HTTPException(422,'Choose one of the listed presets.')
        try:
            with store.connection(atomic=True) as db:
                if data.progression and data.progression.revision!=store.davey._settings(db,uid)[1]:raise ValueError('Davey settings changed. Refresh before saving.')
                store.save_preferences_in(db,uid,data.model_dump(exclude={'progression'}))
                if data.progression:store.davey.save(uid,data.progression.settings,expected_revision=store.davey._settings(db,uid)[1],db=db)
        except ValueError as error:raise HTTPException(409,str(error)) from None
        return {'ok':True}
    @app.post('/api/worker/pairing')
    def pairing(request:Request):
        uid=current(request,True)['user_id'];rate(request)
        return {'code':store.new_pairing(uid),'expiresInSeconds':600}
    @app.post('/api/worker/connect',status_code=201)
    def worker_connect(data:PairingCode,request:Request):
        rate(request);token=store.connect_worker(data.code)
        if not token:raise HTTPException(403,'Pairing code is invalid or expired. Generate a new code in Settings.')
        return {'token':token,'expiresInSeconds':2592000}
    @app.post('/api/worker/heartbeat')
    def heartbeat(request:Request):
        authorization=request.headers.get('authorization','')
        token=authorization[7:] if authorization.startswith('Bearer ') else ''
        if not token or len(token)>100 or not store.worker_heartbeat(token):raise HTTPException(401,'Reconnect your local worker.')
        return {'ok':True,'processingEnabled':False}
    @app.post('/api/worker/revoke')
    def revoke(request:Request):
        store.revoke_workers(current(request,True)['user_id']);return {'ok':True}
    @app.post('/api/reviews')
    def reviews(data:Review,request:Request):
        uid=current(request,True)['user_id']
        if not store.beta_accepted(uid):raise HTTPException(428,'Read and acknowledge the required beta feedback notice in Davey before reviewing clips.')
        if data.localLearning and (data.reasons or data.justification):raise HTTPException(422,'Personal reasons and notes must stay on your companion.')
        allowed={'Strong hook','Funny','Great reaction','Good context','Good timing','Right audience','Other','Weak hook','Not funny','Needs context','Bad timing','Too long','Weak payoff','Wrong audience','Repetitive'}
        if data.decision not in ('approve','reject') or any(reason not in allowed for reason in data.reasons):raise HTTPException(422,'Choose a listed review decision and reason.')
        with store.connection() as db:
            if not db.execute('SELECT 1 FROM candidates WHERE id=? AND user_id=?',(data.candidate_id,uid)).fetchone():raise HTTPException(404,'Candidate not found in your account.')
            pipeline_candidate=db.execute('SELECT 1 FROM pipeline_jobs WHERE id=? AND user_id=?',(data.candidate_id,uid)).fetchone()
        if data.decision=='approve' and pipeline_candidate:
            with store.connection() as db:
                row=db.execute("SELECT a.data FROM clip_artifacts a JOIN candidate_previews p ON p.user_id=a.user_id AND p.job_id=a.clip_id JOIN worker_devices d ON d.token=p.device AND d.user_id=p.user_id WHERE a.user_id=? AND a.clip_id=? AND d.expires>?",(uid,data.candidate_id,__import__('time').time())).fetchone()
            if not row or json.loads(row['data']).get('framing')!='blurred_fit':raise HTTPException(409,'Wait for the captioned mobile preview before approving this clip.')
        try:
            if not store.save_review(uid,data.candidate_id,data.decision,data.reasons,data.justification,local_learning=data.localLearning):raise HTTPException(404,'Candidate not found in your account.')
        except ValueError as error:raise HTTPException(409,str(error)) from None
        from .feedback_receipt import issue_receipt
        return {'ok':True,'localFeedbackReceipt':issue_receipt(store,uid,data.candidate_id,data.decision) if data.localLearning else None}
    from .clip_edits import build_clip_edit_router
    app.include_router(build_clip_edit_router(store))
    @app.post('/api/reports',status_code=201)
    def report(data:SupportReport,request:Request):
        uid=current(request,True)['user_id']
        try:return report_delivery.submit(uid,client_ip(request),data.model_dump())
        except ReportRejected as error:raise HTTPException(error.status,str(error)) from None
    @app.get('/api/reports')
    def report_receipts(request:Request):return {'reports':report_delivery.receipts(current(request)['user_id'])}
    @app.get('/healthz')
    def health():
        with store.connection() as db:db.execute('SELECT 1')
        return {'status':'ok','mode':'prelaunch'}
    @app.get('/api/usage')
    def usage(request:Request):return ledger.snapshot(current(request)['user_id'])
    @app.get('/api/status')
    def status(request:Request):
        uid=current(request)['user_id']
        return {'service':'clipbot','version':1,'worker':{'connected':store.worker_connected(uid)},'davey':{'configured':False},'budget':{'enforced':True,'dispatchEnabled':False},'mode':'prelaunch'}
    @app.get('/api/events')
    def events(request:Request):
        uid=current(request)['user_id']
        from fastapi.responses import StreamingResponse
        import asyncio
        from .pipeline_events import EventStore
        async def feed():
            cursor=0
            while not await request.is_disconnected():
                session=store.session(request.cookies.get('clipbot_session',''))
                if not session or session['user_id']!=uid:return
                for event in EventStore(store).snapshot(uid,cursor=cursor,limit=200):
                    cursor=max(cursor,int(event['id']));yield 'id: '+str(event['id'])+'\ndata: '+json.dumps(event)+'\n\n'
                yield ': keepalive\n\n'
                await asyncio.sleep(3)
        return StreamingResponse(feed(),media_type='text/event-stream',headers={'Cache-Control':'no-cache'})
    @app.get('/api/logs')
    def pipeline_logs(request:Request,after:int=0):
        uid=current(request)['user_id']
        from .pipeline_events import EventStore
        events=EventStore(store)
        if after==0 and not events.snapshot(uid,limit=1):
            from .pipeline_events import CODES
            for job in reversed(app.state.pipeline_jobs.snapshot(uid)):
                events.emit(uid,'job_reported',job_id=job['id'],stage=job['stage'],code=job['errorCode'] if job['errorCode'] in CODES else None,platform=job['source']['platform'],login=job['source']['login'],source='processing',level='error' if job['stage']=='failed' and job['errorCode']!='not_selected' else 'info')
        entries=events.snapshot(uid,cursor=max(0,after),limit=200)
        return {'events':entries,'cursor':max([max(0,after)]+[int(e['id']) for e in entries])}
    @app.get('/api/logs/sessions')
    def debug_sessions(request:Request):
        from .debug_sessions import DebugSessions
        return {'sessions':DebugSessions(store).list(current(request)['user_id'])}
    @app.get('/api/logs/sessions/{session_id}')
    def debug_session_bundle(session_id:str,request:Request):
        from .debug_sessions import DebugSessions
        from fastapi.responses import JSONResponse
        uid=current(request)['user_id']
        try:bundle=DebugSessions(store).bundle(uid,session_id)
        except KeyError:raise HTTPException(404,'Session not found.')
        if bundle['session']['state']!='stopped':raise HTTPException(409,'Logs can be downloaded only after the session ends.')
        return JSONResponse(bundle,headers={'Content-Disposition':'attachment; filename="clipbot-session-'+bundle['session']['id']+'.json"','Cache-Control':'no-store'})
    @app.post('/api/billing/quote')
    def billing_quote(data:QuoteRequest,request:Request):
        current(request,True)
        try:return quote(data.plan,data.custom)
        except ValueError as error:raise HTTPException(422,str(error))
    @app.post('/api/billing/checkout')
    def checkout(data:CheckoutRequest,request:Request):
        uid=current(request,True)['user_id']
        if data.plan=='custom':
            try:expected=quote(data.plan,data.custom)['monthlyCents']
            except ValueError as error:raise HTTPException(422,str(error))
            if data.quotedMonthlyCents!=expected:raise HTTPException(409,'Custom price changed. Review the monthly quote again.')
        try:return billing.start(uid,data.plan,data.custom)
        except BillingUnavailable as error:raise HTTPException(503,str(error))
        except stripe.StripeError as error:
            log_billing_failure(error,'checkout')
            raise HTTPException(503,'Billing is unavailable. No coverage was granted. Try again later.')
    @app.post('/api/billing/webhook')
    async def billing_webhook(request:Request):
        try:event=billing.verify(await request.body(),request.headers.get('stripe-signature',''))
        except BillingUnavailable:raise HTTPException(400,'Payment event could not be verified.')
        try:await run_in_threadpool(billing.receive,event)
        except (BillingUnavailable,stripe.StripeError) as error:
            log_billing_failure(error,'reconciliation')
            raise HTTPException(503,'Payment reconciliation could not finish. Retry delivery.')
        return {'received':True}
    app.include_router(build_customer_access_router(access,current))
    from .billing_api import build_billing_router
    app.include_router(build_billing_router(billing,current))
    from .worker_api import build_worker_router
    worker_router,scouts,pipeline_jobs=build_worker_router(store,current,oauth)
    app.include_router(worker_router)
    from .trigger_settings import build_trigger_router
    app.include_router(build_trigger_router(store,current))
    from .chat_relay import build_chat_router
    chat_router=build_chat_router(store,current,oauth);app.include_router(chat_router);app.state.chat_relay=chat_router.chat_relay
    app.state.scouts=scouts;app.state.pipeline_jobs=pipeline_jobs
    from .companion_api import build_companion_router
    companion_router,companion=build_companion_router(store,current,lambda session:account(session)["isAdmin"],access,oauth,billing)
    app.include_router(companion_router);app.state.companion=companion
    from .analysis_api import build_analysis_router
    from .davey_api import build_davey_router
    davey_router,davey_progression=build_davey_router(store,current)
    app.include_router(davey_router);app.state.davey=davey_progression
    analysis_router,analysis=build_analysis_router(store,current,ledger,admin_uid)
    app.include_router(analysis_router);app.state.analysis=analysis
    from .publication_api import build_publication_router
    publication_router,publication=build_publication_router(store,current,oauth)
    app.include_router(publication_router);app.state.publication=publication
    from .dashboard_metrics import build_dashboard_router
    app.include_router(build_dashboard_router(store,current,oauth))
    from .account_profile import build_account_router
    app.include_router(build_account_router(store,current,rate,account))
    from .account_recovery import AccountRecovery,build_recovery_router
    recovery=AccountRecovery(store,origin);app.state.recovery=recovery
    app.include_router(build_recovery_router(recovery))
    from .customer_admin import build_operator_router
    app.include_router(build_operator_router(store,telemetry,reset_request=recovery.request_reset if recovery.config.get('enabled') else None,ledger=ledger,availability=availability))
    from .legal import build_legal_router
    app.include_router(build_legal_router())
    app.mount('/',StaticFiles(directory=ROOT/'frontend',html=True),name='frontend')
    return app
