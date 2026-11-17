"""Fail-closed reservations in integer microdollars. No provider dispatch here."""
from datetime import datetime,timezone
import json,time
from .billing_usage import paid_period,period_usage,period_activity,BillingPeriodUnavailable
from .owner_showcase import operational_coverage,operational_billing

class BudgetDenied(Exception):pass

def period():
    now=datetime.now(timezone.utc)
    return now.strftime('%Y-%m-%d'),now.strftime('%Y-%m')

class BudgetLedger:
    def __init__(self,store,global_monthly=400_000_000,global_daily=20_000_000,concurrency=3,user_concurrency=1,enabled=False):
        self.store=store;self.global_monthly=global_monthly;self.global_daily=global_daily
        self.concurrency=concurrency;self.user_concurrency=user_concurrency;self.enabled=enabled
    def reserve(self,uid,job_id,max_cost,*,scope_ceiling=None):
        from .customer_access import require_customer_ready
        require_customer_ready(self.store,uid)
        if not self.enabled:raise BudgetDenied('AI is paused by the service owner.')
        if type(max_cost) is not int or max_cost<=0 or max_cost>1_000_000:raise BudgetDenied('Invalid job budget.')
        if not isinstance(job_id,str) or not 1<=len(job_id)<=100:raise BudgetDenied('Invalid request identifier.')
        day,month=period()
        with self.store.connection(atomic=True) as db:
            reserved_at=time.time();reserved_date=datetime.fromtimestamp(reserved_at,timezone.utc);day,month=reserved_date.strftime('%Y-%m-%d'),reserved_date.strftime('%Y-%m')
            if db.execute("SELECT 1 FROM guards WHERE key='reconciliation_stop'").fetchone():raise BudgetDenied('AI is stopped pending spending reconciliation.')
            existing=db.execute('SELECT * FROM jobs WHERE user_id=? AND job_id=?',(uid,job_id)).fetchone()
            # Historical settled records do not authorize a new charge; accounting stays readable.
            if existing and existing['state']=='settled':return dict(existing)
            from .billing_modes import entitlement_allowed
            if not entitlement_allowed(db,uid):raise BudgetDenied('Active plan coverage is required.')
            coverage=operational_coverage(db,uid)
            if not coverage:raise BudgetDenied('An active paid allowance is required.')
            billing=operational_billing(db,uid)
            if billing and (billing['status']!='active' or billing['expires']<=reserved_at):raise BudgetDenied('Your paid coverage is inactive or expired.')
            try:billing_cycle=paid_period(db,uid,reserved_at)
            except BillingPeriodUnavailable as error:raise BudgetDenied(str(error)) from None
            # Reusing an outstanding reservation still requires live paid authorization.
            if existing:return dict(existing)
            from .launch_caps import effective_caps
            coverage=effective_caps(db,uid,coverage,billing)
            user_usage=period_usage(db,uid,billing_cycle,month)
            if billing and coverage['monthly_reviews'] is not None and user_usage['reviews']>=coverage['monthly_reviews']:raise BudgetDenied('Monthly review allowance reached.')
            def total(where,args):
                return db.execute('SELECT COALESCE(SUM(spent+reserved),0) FROM jobs WHERE '+where,args).fetchone()[0]
            if scope_ceiling is not None:
                if type(scope_ceiling) is not int or not 0<scope_ceiling<=1000000:raise BudgetDenied('Invalid analysis scope ceiling.')
                scope_usage=period_usage(db,uid,billing_cycle,month,pipeline_only=True)
                if scope_usage['spent']+scope_usage['reserved']+max_cost>scope_ceiling:raise BudgetDenied('Initial live analysis test spending ceiling reached.')
            prefs=db.execute('SELECT data FROM preferences WHERE user_id=?',(uid,)).fetchone()
            preset=json.loads(prefs['data']).get('usagePreset','paused') if prefs else 'paused'
            daily_cap={'paused':0,'light':250000,'balanced':500000,'busy':1000000}.get(preset,0)
            if coverage['daily_ai'] is not None:daily_cap=min(daily_cap,coverage['daily_ai'])
            if total('user_id=? AND day=?',(uid,day))+max_cost>daily_cap:raise BudgetDenied('Your selected daily spending preset pauses further reviews.')
            global_used=total('month=?',(month,))
            if global_used+max_cost>self.global_monthly or total('day=?',(day,))+max_cost>self.global_daily:raise BudgetDenied('Service spending stop reached. No overage is charged.')
            if user_usage['spent']+user_usage['reserved']+max_cost>coverage['user_monthly']:raise BudgetDenied('Your AI spending allowance is reached.')
            reviews=db.execute('SELECT COUNT(*) FROM jobs WHERE user_id=? AND day=?',(uid,day)).fetchone()[0]
            if reviews>=coverage['review_daily']:raise BudgetDenied('Your daily review allowance is reached.')
            active=db.execute("SELECT COUNT(*) FROM jobs WHERE state='reserved'").fetchone()[0]
            own=db.execute("SELECT COUNT(*) FROM jobs WHERE state='reserved' AND user_id=?",(uid,)).fetchone()[0]
            # At 80% of the global monthly ceiling, automatically reduce dispatch to one.
            limit=1 if global_used>=self.global_monthly*0.8 else self.concurrency
            if active>=limit or own>=self.user_concurrency:raise BudgetDenied('Davey is throttled. Please wait for an active review to finish.')
            db.execute('INSERT INTO jobs(user_id,job_id,day,month,reserved) VALUES(?,?,?,?,?)',(uid,job_id,day,month,max_cost))
            db.execute('INSERT INTO job_timestamps VALUES(?,?,?)',(uid,job_id,reserved_at))
            return dict(db.execute('SELECT * FROM jobs WHERE user_id=? AND job_id=?',(uid,job_id)).fetchone())
    def settle(self,uid,job_id,actual_cost,input_tokens,output_tokens):
        if any(type(x) is not int or x<0 for x in (actual_cost,input_tokens,output_tokens)):raise ValueError('Invalid usage')
        with self.store.connection(atomic=True) as db:
            job=db.execute('SELECT * FROM jobs WHERE user_id=? AND job_id=?',(uid,job_id)).fetchone()
            if not job:raise ValueError('Reservation not found')
            if job['state']=='settled':return
            overrun=actual_cost>job['reserved']
            if overrun:db.execute("INSERT OR REPLACE INTO guards VALUES('reconciliation_stop','provider_overrun')")
            db.execute("UPDATE jobs SET spent=?,reserved=0,input_tokens=?,output_tokens=?,state='settled' WHERE user_id=? AND job_id=?",(actual_cost,input_tokens,output_tokens,uid,job_id))
        if overrun:raise ValueError('Provider cost exceeded reservation; AI is stopped pending reconciliation')
    def snapshot(self,uid):
        now=time.time();date=datetime.fromtimestamp(now,timezone.utc);day,month=date.strftime('%Y-%m-%d'),date.strftime('%Y-%m');billing_cycle=None;reconciliation=False
        with self.store.connection() as db:
            billing=operational_billing(db,uid)
            try:billing_cycle=paid_period(db,uid,now,require_active=bool(billing and billing['status']=='active' and billing['expires']>now))
            except BillingPeriodUnavailable:reconciliation=bool(billing and billing['status']=='active' and billing['expires']>now)
            row=period_usage(db,uid,billing_cycle,month)
            daily=db.execute('SELECT COUNT(*) FROM jobs WHERE user_id=? AND day=?',(uid,day)).fetchone()[0]
            activity=period_activity(db,uid,billing_cycle,month)
            global_used=db.execute('SELECT COALESCE(SUM(spent+reserved),0) FROM jobs WHERE month=?',(month,)).fetchone()[0]
            raw_coverage=operational_coverage(db,uid)
            from .launch_caps import effective_caps
            launch=effective_caps(db,uid,raw_coverage,billing) if raw_coverage else None
            stopped=bool(db.execute("SELECT 1 FROM guards WHERE key='reconciliation_stop'").fetchone())
        coverage=self.store.coverage(uid)
        if coverage and launch:
            coverage={**coverage,'review_daily':min(coverage['review_daily'],launch['review_daily']),'user_monthly':min(coverage['user_monthly'],launch['user_monthly'])}
        return {'inputTokens':row['inputs'],'outputTokens':row['outputs'],'spentMicros':row['spent'],'reservedMicros':row['reserved'],'reviewsToday':daily,'reviewsMonth':row['reviews'],'reviewLimit':coverage['review_daily'] if coverage and not reconciliation else 0,'monthlyReviewLimit':launch['monthly_reviews'] if launch else None,'spendLimitMicros':coverage['user_monthly'] if coverage and not reconciliation else 0,'activity':activity,'period':month,'billingPeriod':billing_cycle,'periodReconciliationRequired':reconciliation,'resetTimezone':'UTC','throttled':stopped or reconciliation or not self.enabled or global_used>=self.global_monthly*0.8,'aiEnabled':self.enabled and not stopped and not reconciliation and bool(coverage),'globalStop':stopped or global_used>=self.global_monthly}
