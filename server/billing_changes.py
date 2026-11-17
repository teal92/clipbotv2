"""Owned, idempotent mode-bound plan changes. Usage history is never reset."""
import math
import secrets
import time
from urllib.parse import urlsplit
from .billing_usage import valid_period
from .pricing import quote
from .billing_modes import resource_mode,bind_mode


def schema(db):
    db.execute('''CREATE TABLE IF NOT EXISTS billing_changes(
        id TEXT PRIMARY KEY,user_id TEXT NOT NULL,subscription TEXT NOT NULL,
        from_plan TEXT NOT NULL,to_plan TEXT NOT NULL,kind TEXT NOT NULL,
        state TEXT NOT NULL,created INTEGER NOT NULL,starts REAL NOT NULL,ends REAL NOT NULL,
        item_id TEXT NOT NULL,ai_limit INTEGER NOT NULL,review_limit INTEGER,
        schedule_id TEXT NOT NULL DEFAULT '',payment_url TEXT NOT NULL DEFAULT '')''')
    db.execute('CREATE INDEX IF NOT EXISTS billing_changes_user ON billing_changes(user_id,created)')
    db.execute('CREATE TABLE IF NOT EXISTS billing_change_refresh(user_id TEXT PRIMARY KEY,checked REAL NOT NULL)')


def safe_payment_url(url):
    if not isinstance(url,str):return ''
    try:
        parsed=urlsplit(url)
        return url if parsed.scheme=='https' and parsed.hostname=='invoice.stripe.com' and not parsed.username and not parsed.password and parsed.port in (None,443) else ''
    except ValueError:return ''


def public(row,mode="test"):
    if not row:return None
    return {'id':row['id'],'plan':row['to_plan'],'kind':row['kind'],'status':row['state'],
            'effectiveAt':row['ends'] if row['kind']=='downgrade' else row['created'],
            'limitsEffectiveAt':row['created'] if row['kind']=='downgrade' and row['state'] in ('scheduled','applied') else None,
            'paymentUrl':row['payment_url'],'sandbox':mode=='test'}


def status(billing,uid):
    with billing.store.connection() as db:
        schema(db)
        if resource_mode(db,'state',uid)!=billing.mode:return None
        row=db.execute('SELECT c.* FROM billing_changes c JOIN billing_state b ON b.user_id=c.user_id AND b.subscription=c.subscription WHERE c.user_id=? ORDER BY c.created DESC,c.rowid DESC LIMIT 1',(uid,)).fetchone()
        result=public(row,billing.mode)
        if row and row['to_plan']=='custom':
            from .custom_billing import config,proposal
            result['custom']=config(db,'change',row['id'])
            result['monthlyCents']=proposal('custom',result['custom'])['monthlyCents']
        return result


def refresh(billing,uid):
    from .billing import BillingUnavailable
    with billing.store.connection(atomic=True) as db:
        schema(db)
        state=db.execute('SELECT subscription FROM billing_state WHERE user_id=?',(uid,)).fetchone()
        last=db.execute('SELECT checked FROM billing_change_refresh WHERE user_id=?',(uid,)).fetchone()
        if state and resource_mode(db,'state',uid)!=billing.mode:raise BillingUnavailable('Subscription belongs to a different billing mode.')
        if state and billing.ready:
            if last and time.time()-last['checked']<10:raise BillingUnavailable('Wait ten seconds before refreshing billing again.')
            db.execute('INSERT OR REPLACE INTO billing_change_refresh VALUES(?,?)',(uid,time.time()))
    if state and billing.ready:
        billing.receive({'id':'change-refresh-'+secrets.token_hex(16),'livemode':billing.live,'type':'customer.subscription.updated','data':{'object':{'id':state['subscription']}}})
    return status(billing,uid)


def change(billing,uid,target,custom=None):
    from .billing import BillingUnavailable
    from .custom_billing import proposal,config,bind,validate_product
    new=proposal(target,custom)
    if not billing.ready or not billing.price_id(target,custom):raise BillingUnavailable('Choose an available plan.')
    if target=='custom':validate_product(billing)
    billing.validate_live_configuration()
    with billing.store.connection() as db:
        schema(db)
        state=db.execute('SELECT * FROM billing_state WHERE user_id=?',(uid,)).fetchone()
        if state and db.execute('SELECT 1 FROM billing_access_revocations WHERE user_id=? AND subscription=? AND mode=?',(uid,state['subscription'],billing.mode)).fetchone():raise BillingUnavailable('Cancellation is in progress or completed. Reconcile billing before changing plans.')
        old_custom=config(db,'state',uid)
        pending=db.execute("SELECT * FROM billing_changes WHERE user_id=? AND subscription=? AND state IN ('requested','payment_pending','scheduled') ORDER BY created DESC,rowid DESC LIMIT 1",(uid,state['subscription'] if state else '')).fetchone()
    if state:
        with billing.store.connection() as db:
            if resource_mode(db,'state',uid)!=billing.mode:raise BillingUnavailable('Subscription belongs to a different billing mode.')
    if not state or state['status']!='active' or state['expires']<=time.time():
        raise BillingUnavailable('An active paid subscription is required to change plans.')
    if pending:
        if pending['to_plan']!=target or target=='custom' and config_from_store(billing,'change',pending['id'])!=custom:raise BillingUnavailable('Resolve the pending plan change before requesting another.')
        if pending['state']!='requested':return public(pending,billing.mode)
        if time.time()-pending['created']>=23*3600:raise BillingUnavailable('The uncertain change requires billing reconciliation; no new charge was started.')
        row=dict(pending)
    else:
        sub=billing.provider.subscription(state['subscription'])
        items=sub.get('items',{}).get('data',[]);item=items[0] if len(items)==1 else {}
        starts=item.get('current_period_start',sub.get('current_period_start'))
        ends=item.get('current_period_end',sub.get('current_period_end'))
        with billing.store.connection() as db:
            expired=db.execute("SELECT 1 FROM billing_changes WHERE user_id=? AND subscription=? AND from_plan=? AND state='expired' AND starts=? AND ends=?",(uid,state['subscription'],state['plan'],starts,ends)).fetchone()
        prior_paid=bool(expired and (sub.get('latest_invoice') or {}).get('status')=='void')
        if (sub.get('livemode') is not billing.live or sub.get('id')!=state['subscription'] or sub.get('customer')!=state['customer'] or
            sub.get('metadata',{}).get('request_id')!=state['request_id'] or sub.get('status')!='active' or
            sub.get('collection_method')!='charge_automatically' or sub.get('cancel_at_period_end') or sub.get('pause_collection') or
            sub.get('pending_update') or sub.get('schedule') or not valid_period(starts,ends) or ends!=state['expires'] or
            not item.get('id') or not billing.valid_price(item,state['plan'],old_custom if state['plan']=='custom' else None) or ((sub.get('latest_invoice') or {}).get('status')!='paid' and not prior_paid)):
            raise BillingUnavailable('This subscription needs billing attention before a plan change.')
        if target==state['plan'] and (target!='custom' or custom==old_custom):return {'status':'unchanged','plan':target,'sandbox':not billing.live}
        target_price=billing.provider.price(billing.price_id(target,custom))
        if not target_price.get('active') or not billing.valid_price({'quantity':1,'price':target_price},target,custom):
            raise BillingUnavailable('The target price does not match the configured plan.')
        # Reject complex subscriptions rather than dropping discounts/taxes/settings in a schedule.
        if any(sub.get(k) for k in ('discounts','default_tax_rates','trial_end','billing_thresholds','on_behalf_of','transfer_data','application_fee_percent')) or item.get('discounts') or item.get('tax_rates') or (sub.get('automatic_tax') or {}).get('enabled'):
            raise BillingUnavailable('This subscription requires assisted billing management.')
        old=proposal(state['plan'],old_custom if state['plan']=='custom' else None)
        kind='upgrade' if new['monthlyCents']>old['monthlyCents'] else 'downgrade'
        created=int(time.time());fraction=max(0,min(1,(ends-created)/(ends-starts)))
        coverage=billing.store.coverage(uid,include_showcase=False)
        if not coverage:raise BillingUnavailable('Paid coverage is not available.')
        ai_limit=coverage['user_monthly']+math.floor((new['aiCeilingMicros']-old['aiCeilingMicros'])*fraction) if kind=='upgrade' else min(coverage['user_monthly'],new['aiCeilingMicros'])
        reviews=new['monthlyReviews']
        if kind=='upgrade' and reviews is not None and old['monthlyReviews'] is not None:
            reviews=state['monthly_reviews']+math.floor((reviews-old['monthlyReviews'])*fraction)
        elif kind=='downgrade' and state['monthly_reviews'] is not None:
            reviews=state['monthly_reviews'] if reviews is None else min(reviews,state['monthly_reviews'])
        row={'id':secrets.token_hex(16),'user_id':uid,'subscription':state['subscription'],'from_plan':state['plan'],
             'to_plan':target,'kind':kind,'state':'requested','created':created,'starts':starts,'ends':ends,
             'item_id':item['id'],'ai_limit':ai_limit,'review_limit':reviews,'schedule_id':'','payment_url':''}
        with billing.store.connection(atomic=True) as db:
            schema(db)
            # Recheck after provider reads; concurrent clicks cannot create competing changes.
            actual=db.execute('SELECT * FROM billing_state WHERE user_id=?',(uid,)).fetchone()
            existing=db.execute("SELECT * FROM billing_changes WHERE user_id=? AND subscription=? AND state IN ('requested','payment_pending','scheduled') ORDER BY created DESC,rowid DESC LIMIT 1",(uid,state['subscription'])).fetchone()
            if existing:
                if existing['to_plan']!=target or target=='custom' and config(db,'change',existing['id'])!=custom:raise BillingUnavailable('Another plan change is pending.')
                row=dict(existing)
                if row['state']!='requested':return public(row,billing.mode)
            elif dict(actual)!=dict(state):raise BillingUnavailable('Billing changed. Refresh before trying again.')
            else:
                keys=list(row)
                db.execute('INSERT INTO billing_changes('+','.join(keys)+') VALUES('+','.join('?' for _ in keys)+')',tuple(row[k] for k in keys))
                bind_mode(db,'change',row['id'],billing.mode)
                bind(db,'change',row['id'],custom if target=='custom' else None)
                bind(db,'change_from',row['id'],old_custom if state['plan']=='custom' else None)
    # The operation commits before network calls. A lost response reuses identical parameters/key.
    key='clipbot-plan-change-'+row['id']
    target_custom=config_from_store(billing,'change',row['id'])
    old_custom=config_from_store(billing,'change_from',row['id'])
    if row['kind']=='upgrade':
        params={'items':[{'id':row['item_id'],'price':billing.price_id(target,target_custom),'quantity':1}],
                'payment_behavior':'pending_if_incomplete','proration_behavior':'always_invoice',
                'proration_date':row['created'],'billing_cycle_anchor':{'type':'unchanged'},'expand':['latest_invoice']}
        result=billing.provider.upgrade(row['subscription'],params,key)
        if result.get('id')!=row['subscription'] or result.get('livemode') is not billing.live:
            raise BillingUnavailable('The plan change response could not be verified.')
        with billing.store.connection() as db:
            db.execute("UPDATE billing_changes SET state=CASE WHEN state='requested' THEN 'payment_pending' ELSE state END,payment_url=? WHERE id=?",(safe_payment_url((result.get('latest_invoice') or {}).get('hosted_invoice_url')),row['id']))
        billing.receive({'id':'change-response-'+row['id'],'livemode':billing.live,'type':'customer.subscription.updated','data':{'object':{'id':row['subscription']}}})
    else:
        result=billing.provider.downgrade(row['subscription'],billing.price_id(row['from_plan'],old_custom),billing.price_id(target,target_custom),row['starts'],row['ends'],key)
        if result.get('subscription')!=row['subscription'] or result.get('livemode') is not billing.live or not result.get('id'):
            raise BillingUnavailable('The scheduled change could not be verified.')
        with billing.store.connection(atomic=True) as db:
            db.execute("UPDATE billing_changes SET state=CASE WHEN state='requested' THEN 'scheduled' ELSE state END,schedule_id=? WHERE id=?",(result['id'],row['id']))
        # Reconcile the verified paid item while projecting lower capacities separately.
        # Never replace its paid-price baseline with a future scheduled price.
        billing.receive({'id':'change-response-'+row['id'],'livemode':billing.live,'type':'customer.subscription.updated','data':{'object':{'id':row['subscription']}}})
    return status(billing,uid)


def resolve(billing,db,sub,request,item,starts,ends):
    """Only a recorded user-authorized target can replace the verified checkout plan."""
    schema(db);uid=request['user_id']
    if sub.get('status') in ('canceled','incomplete_expired'):
        db.execute("UPDATE billing_changes SET state='canceled',payment_url='' WHERE user_id=? AND subscription=? AND state IN ('requested','payment_pending','scheduled')",(uid,sub['id']))
    existing=db.execute('SELECT * FROM billing_state WHERE user_id=?',(uid,)).fetchone()
    baseline=existing['plan'] if existing and existing['subscription']==sub['id'] else request['plan']
    row=db.execute("SELECT * FROM billing_changes WHERE user_id=? AND subscription=? AND state IN ('requested','payment_pending','scheduled','applied','expired') ORDER BY created DESC,rowid DESC LIMIT 1",(uid,sub['id'])).fetchone()
    if row and resource_mode(db,'change',row['id'])!=billing.mode:row=None
    from .custom_billing import config,bind
    baseline_custom=config(db,'state',uid) if existing and existing['subscription']==sub['id'] else config(db,'request',request['id'])
    valid_current=billing.valid_price(item,baseline,baseline_custom if baseline=='custom' else None)
    target_custom=config(db,'change',row['id']) if row else None
    target_valid=bool(row and billing.valid_price(item,row['to_plan'],target_custom if row['to_plan']=='custom' else None))
    current_period=valid_period(starts,ends)
    due=bool(row and current_period and (row['kind']=='upgrade' and (starts==row['starts'] and ends==row['ends'] or starts>=row['ends']) or row['kind']=='downgrade' and starts>=row['ends']))
    # Identical prices cannot prove a capacity change: verify the recorded schedule.
    if row and row['kind']=='downgrade' and row['state']!='applied' and due:
        old_custom=config(db,'change_from',row['id'])
        same_price=billing.price_id(row['from_plan'],old_custom)==billing.price_id(row['to_plan'],target_custom)
        if same_price:
            due=False
            if row['state']=='scheduled' and row['schedule_id']:
                schedule=billing.provider.schedule(row['schedule_id'])
                if schedule.get('status')=='canceled':
                    db.execute("UPDATE billing_changes SET state='canceled' WHERE id=?",(row['id'],))
                phases=schedule.get('phases') or []
                target=[p for p in phases if p.get('start_date')==int(row['ends'])]
                phase=target[0] if len(target)==1 else {}
                items=phase.get('items') or [];scheduled_item=items[0] if len(items)==1 else {}
                price=scheduled_item.get('price');price_id=price.get('id') if isinstance(price,dict) else price
                owned=schedule.get('subscription')==sub['id'] or schedule.get('released_subscription')==sub['id']
                progressed=schedule.get('status')=='completed' or schedule.get('status')=='active' and (schedule.get('current_phase') or {}).get('start_date')==int(row['ends'])
                due=bool(schedule.get('id')==row['schedule_id'] and schedule.get('livemode') is billing.live and owned and progressed and price_id==billing.price_id(row['to_plan'],target_custom) and type(scheduled_item.get('quantity')) is int and scheduled_item['quantity']==1)
    applied=bool(target_valid and row['state']!='expired' and (row['state']=='applied' or due) and (sub.get('latest_invoice') or {}).get('status')=='paid' and not sub.get('pending_update'))
    if applied:
        db.execute("UPDATE billing_changes SET state='applied',payment_url='' WHERE id=?",(row['id'],))
        plan=row['to_plan']
        bind(db,'state',uid,target_custom if plan=='custom' else None)
        adjustment=dict(row) if row['kind']=='upgrade' and starts==row['starts'] and ends==row['ends'] else None
    else:plan=baseline;adjustment=None
    # Retain previously paid access for the unchanged original item during an unpaid upgrade.
    preserve=bool(row and row['kind']=='upgrade' and row['state'] in ('requested','payment_pending','expired') and valid_current and
                  existing and existing['status']=='active' and existing['expires']==ends and ends>time.time() and
                  starts==row['starts'] and ends==row['ends'] and not sub.get('pause_collection') and sub.get('status')=='active')
    if preserve and row['state']!='expired' and not sub.get('pending_update') and (sub.get('latest_invoice') or {}).get('status')=='void':
        db.execute("UPDATE billing_changes SET state='expired',payment_url='' WHERE id=?",(row['id'],))
    if row and row['kind']=='upgrade' and row['state'] in ('requested','payment_pending') and valid_current and current_period and starts>=row['ends'] and not sub.get('pending_update') and (sub.get('latest_invoice') or {}).get('status')=='paid':
        db.execute("UPDATE billing_changes SET state='expired',payment_url='' WHERE id=?",(row['id'],))
    if row and row['kind']=='downgrade' and row['state']=='scheduled' and valid_current and not applied:
        schedule=sub.get('schedule');schedule_id=schedule.get('id') if isinstance(schedule,dict) else schedule
        if schedule_id!=row['schedule_id']:
            db.execute("UPDATE billing_changes SET state='canceled' WHERE id=?",(row['id'],))
    # Keep earlier prorated entitlement if a second upgrade is pending.
    if not adjustment:
        prior=db.execute("SELECT * FROM billing_changes WHERE user_id=? AND subscription=? AND to_plan=? AND kind='upgrade' AND state='applied' AND starts=? AND ends=? ORDER BY created DESC,rowid DESC LIMIT 1",(uid,sub['id'],plan,starts,ends)).fetchone()
        if prior:adjustment=dict(prior)
    return plan,adjustment,preserve


def config_from_store(billing,resource,id):
    from .custom_billing import config
    with billing.store.connection() as db:return config(db,resource,id)


def capacity_snapshot(db,uid,subscription,starts,ends):
    """Lower caps for a confirmed schedule; paid plan remains the price validator.

    A same-price Custom edit can mix decreases and increases. Only decreases
    apply now; increases still require the verified renewal phase.
    """
    schema(db)
    row=db.execute("SELECT * FROM billing_changes WHERE user_id=? AND subscription=? AND kind='downgrade' AND state='scheduled' AND schedule_id<>'' AND starts=? AND ends=? ORDER BY created DESC,rowid DESC LIMIT 1",(uid,subscription,starts,ends)).fetchone()
    if not row or resource_mode(db,'change',row['id'])!=resource_mode(db,'state',uid):return None
    from .custom_billing import config,proposal
    old=proposal(row['from_plan'],config(db,'change_from',row['id']) if row['from_plan']=='custom' else None)
    target=proposal(row['to_plan'],config(db,'change',row['id']) if row['to_plan']=='custom' else None)
    def lower(a,b):return b if a is None else a if b is None else min(a,b)
    quantities={key:lower(old['quantities'].get(key),target['quantities'].get(key)) for key in old['quantities']}
    return {'quantities':quantities,'aiCeilingMicros':min(old['aiCeilingMicros'],row['ai_limit']),'monthlyReviews':lower(old['monthlyReviews'],row['review_limit'])}
