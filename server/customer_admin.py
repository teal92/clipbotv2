"""Private C2 service boundary. Explicit customer projection never selects credentials."""
import hmac, json, os, re, time
from pathlib import Path
from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, Request, HTTPException
from pydantic import BaseModel,ConfigDict,StrictBool,StrictInt,Field
from .admin import metrics, DEV_EMAIL
from .billing_usage import paid_period,period_usage,BillingPeriodUnavailable

def list_customers(store,offset=0,now=None):
    now=time.time() if now is None else now
    today=datetime.fromtimestamp(now,timezone.utc).date();month=today.strftime('%Y-%m')
    days=[(today-timedelta(days=i)).isoformat() for i in range(6,-1,-1)]
    with store.connection() as db:
        users=db.execute('SELECT id,email,name,created FROM users WHERE email!=? ORDER BY created DESC,id LIMIT 101 OFFSET ?',(DEV_EMAIL,offset)).fetchall()
        result=[]
        for user in users[:100]:
            uid=user['id'];coverage=store.coverage(uid)
            billing=db.execute('SELECT plan,status,expires,monthly_reviews FROM billing_state WHERE user_id=?',(uid,)).fetchone()
            billing_cycle=None;period_unavailable=False
            try:billing_cycle=paid_period(db,uid,now,require_active=False)
            except BillingPeriodUnavailable:period_unavailable=True
            recorded=period_usage(db,uid,billing_cycle,month)
            usage=(recorded['spent']+recorded['reserved'],recorded['reviews'])
            daily=db.execute('SELECT COUNT(*),COALESCE(SUM(spent+reserved),0) FROM jobs WHERE user_id=? AND day=?',(uid,days[-1])).fetchone()
            activity={r[0]:r[1] for r in db.execute('SELECT day,SUM(input_tokens+output_tokens) FROM jobs WHERE user_id=? AND day>=? AND day<=? GROUP BY day',(uid,days[0],days[-1]))}
            prefs=db.execute('SELECT data FROM preferences WHERE user_id=?',(uid,)).fetchone()
            preset=json.loads(prefs[0]).get('usagePreset','paused') if prefs else 'paused'
            daily_cap={'paused':0,'light':250000,'balanced':500000,'busy':1000000}.get(preset,0)
            caps=['billing_period_unavailable'] if period_unavailable else []
            if coverage:
                if usage[0]>=coverage['user_monthly']:caps.append('monthly_budget')
                if daily[0]>=coverage['review_daily']:caps.append('daily_reviews')
                if daily[1]>=daily_cap:caps.append('daily_preset')
            if billing and billing['monthly_reviews'] is not None and usage[1]>=billing['monthly_reviews']:caps.append('monthly_reviews')
            points=[{'day':d,'tokens':activity.get(d,0)} for d in days]
            result.append(dict(user,plan=billing['plan'] if billing else ('manual allowance' if coverage else 'no active plan'),planStatus=billing['status'] if billing else ('active' if coverage else 'inactive'),passwordStatus='Set; never readable',resetAvailable=False,resetReason='Verified account email delivery is not configured.',usage={'tokens7Days':sum(p['tokens'] for p in points),'activity':points,'billingPeriod':billing_cycle,'periodReconciliationRequired':period_unavailable,'reviewsBillingPeriod':usage[1],'monthlyReviewLimit':billing['monthly_reviews'] if billing else None,'monthlySpentMicros':usage[0],'monthlyLimitMicros':coverage['user_monthly'] if coverage else 0,'reviewsToday':daily[0],'dailyReviewLimit':coverage['review_daily'] if coverage else 0},limitsReached=caps,abuseStatus='Not assessed',abuseSignals=[]))
    return {'customers':result,'nextOffset':offset+100 if len(users)>100 else None,'source':'ClipBot account database','generatedAt':now,'resetTimezone':'UTC'}

def operator_key(value,path):
    if value:return value.strip()
    try:
        path=Path(path)
        if path.is_symlink() or path.stat().st_size>256:return ''
        return path.read_text(encoding='utf-8').strip()
    except OSError:return ''

class AvailabilityChange(BaseModel):
    model_config=ConfigDict(extra='forbid')
    online:StrictBool
    expectedRevision:StrictInt=Field(ge=0)
    confirmed:StrictBool


def build_operator_router(store,telemetry,service_key=None,reset_request=None,ledger=None,availability=None):
    router=APIRouter(prefix='/api/operator')
    key=operator_key(os.getenv('CLIPBOT_C2_SERVICE_KEY',''),os.getenv('CLIPBOT_C2_SERVICE_KEY_FILE',str(store.path.parent/'clipbot-c2.key'))) if service_key is None else service_key
    def authorize(request):
        if len(key)<32:raise HTTPException(404,'Not found')
        provided=request.headers.get('Authorization','')
        if not hmac.compare_digest(provided.encode(),('Bearer '+key).encode()):raise HTTPException(401,'C2 service authentication required')
    def audit(action,uid=None):
        with store.connection() as db:
            db.execute('CREATE TABLE IF NOT EXISTS operator_audit(id INTEGER PRIMARY KEY,created REAL NOT NULL,action TEXT NOT NULL,target TEXT)')
            db.execute('INSERT INTO operator_audit(created,action,target) VALUES(?,?,?)',(time.time(),action,uid))
    @router.get('/availability')
    def get_availability(request:Request):
        authorize(request)
        if availability is None:raise HTTPException(503,'Website control is unavailable.')
        return availability.snapshot()
    @router.post('/availability')
    def change_availability(data:AvailabilityChange,request:Request):
        authorize(request)
        if not data.confirmed:raise HTTPException(400,'Explicit owner confirmation is required.')
        if availability is None:raise HTTPException(503,'Website control is unavailable.')
        result=availability.change(data.online,data.expectedRevision)
        audit('website_reopened' if data.online else 'website_closed')
        return result
    @router.get('/metrics')
    def get_metrics(request:Request,period:str='week'):
        authorize(request)
        if period not in ('day','week','month','year','all'):raise HTTPException(422,'Choose day, week, month, year or all.')
        audit('metrics_read')
        from .capacity_policy import planning_policy
        from .custom_forecast import custom_forecast
        from .usage_capacity import capacity_usage
        from .budgets import BudgetLedger
        budget=ledger if ledger is not None else BudgetLedger(store)
        from .site_visitors import SiteVisitors
        return {**metrics(store,period=period),'visitors':SiteVisitors(store).snapshot(),'serverPerformance':telemetry.snapshot() if telemetry else None,
                'planningPolicy':planning_policy(budget),'customForecast':custom_forecast(store),'capacityUsage':capacity_usage(store,budget)}
    @router.get('/edge-status')
    def edge_status(request:Request,probe_ip:str='198.51.100.42'):
        authorize(request)
        import ipaddress
        from .client_ip import client_ip
        try:
            ipaddress.ip_address(probe_ip)
            peer=ipaddress.ip_address(request.client.host)
            values=request.headers.getlist('cf-connecting-ip')
            claimed=ipaddress.ip_address(values[0]) if len(values)==1 else None
        except ValueError:raise HTTPException(422,'Invalid ingress probe.')
        ray=request.headers.get('cf-ray','')
        return {'renderHosted':os.getenv('RENDER')=='true','socketPeerPrivate':peer.is_private or peer.is_loopback,
                'socketPeerLoopback':peer.is_loopback,'socketPeerClass':str(ipaddress.ip_network(str(peer)+('/32' if peer.version==4 else '/128'))),
                'cloudflareRayPresent':bool(re.fullmatch(r'[a-fA-F0-9]{16,32}-[A-Z0-9]{3}',ray)),
                'cloudflareClientPublic':bool(claimed and claimed.is_global),'forgedClientHeaderReachedOrigin':bool(claimed and str(claimed)==probe_ip),
                'forwardedForContainsProbe':probe_ip in request.headers.get('x-forwarded-for','').split(', '),
                'trustedClientAttribution':bool(claimed and client_ip(request)==str(claimed)),
                'profileConfigured':os.getenv('CLIPBOT_TRUSTED_EDGE') in ('render-cloudflare','cloudflare-verified')}
    @router.get('/customers')
    def customers(request:Request,offset:int=0):
        authorize(request)
        if not 0<=offset<=1000000:raise HTTPException(400,'Invalid page')
        audit('customers_read');result=list_customers(store,offset)
        for customer in result['customers']:
            customer['resetAvailable']=reset_request is not None
            if reset_request:customer['resetReason']='Send a single-use, expiring link to the account email. No password is shown.'
        return result
    @router.post('/customers/{uid}/reset')
    async def reset(uid:str,request:Request):
        authorize(request)
        if not re.fullmatch(r'[a-f0-9]{32}',uid):raise HTTPException(400,'Invalid account')
        if not reset_request:
            audit('reset_blocked_unconfigured',uid)
            raise HTTPException(409,'Secure reset requires account email delivery. No password was changed.')
        try:data=await request.json()
        except ValueError:raise HTTPException(400,'Explicit owner approval required')
        if not isinstance(data,dict) or data.get('approved') is not True:raise HTTPException(400,'Explicit owner approval required')
        if not store.user(uid):raise HTTPException(404,'Account not found')
        audit('reset_requested',uid)
        try:
            from starlette.concurrency import run_in_threadpool
            await run_in_threadpool(reset_request,uid)
        except ValueError:
            audit('reset_delivery_failed',uid)
            raise HTTPException(409,'Secure reset delivery is unavailable. No password was changed.') from None
        audit('reset_delivery_requested',uid)
        return {'ok':True,'message':'If delivery succeeds, the customer will receive a single-use reset link.'}
    return router
