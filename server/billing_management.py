"""Owned cancellation and Stripe-hosted management; uncertain mutations reconcile."""
import secrets,time
from urllib.parse import urlsplit
from .billing_modes import resource_mode

def owned(billing,db,uid):
    from .billing import BillingUnavailable
    row=db.execute('SELECT * FROM billing_state WHERE user_id=?',(uid,)).fetchone()
    if not billing.ready or not row or resource_mode(db,'state',uid)!=billing.mode:
        raise BillingUnavailable('An owned subscription in the current billing mode is required.')
    return row

def verified(billing,row):
    from .billing import BillingUnavailable
    sub=billing.provider.subscription(row['subscription'])
    if sub.get('livemode') is not billing.live or sub.get('id')!=row['subscription'] or sub.get('customer')!=row['customer'] or sub.get('metadata',{}).get('request_id')!=row['request_id']:
        raise BillingUnavailable('Subscription ownership could not be verified.')
    return sub

def public(row):
    if not row:return None
    return {'status':'reconciliation_required' if row['status']=='requested' else row['status'],'effectiveAt':row['ends'],'sandbox':row['mode']=='test'}

def cancellation_status(billing,uid):
    with billing.store.connection() as db:
        return public(db.execute('SELECT c.* FROM billing_cancellations c JOIN billing_state b ON b.user_id=c.user_id AND b.subscription=c.subscription WHERE c.user_id=? AND c.mode=? ORDER BY c.created DESC LIMIT 1',(uid,billing.mode)).fetchone())

def cancel(billing,uid):
    from .immediate_cancellation import cancel as cancel_now
    return cancel_now(billing,uid)


def reconcile_cancellation(billing,db,uid,sub,ends):
    from .billing_schedule_cancellation import at_period_end
    status='canceled' if sub.get('status') in ('canceled','incomplete_expired') else 'scheduled' if at_period_end(sub,ends) else None
    if status=='canceled':
        from .immediate_cancellation import revoke
        revoke(db,uid,sub['id'],billing.mode,time.time())
        ends=sub.get('ended_at') or time.time()
        if db.execute("SELECT 1 FROM sqlite_master WHERE name='billing_changes'").fetchone():
            db.execute("UPDATE billing_changes SET state='canceled',payment_url='' WHERE user_id=? AND subscription=? AND state IN ('requested','payment_pending','scheduled') AND COALESCE((SELECT mode FROM billing_modes WHERE resource='change' AND id=billing_changes.id),'test')=?",(uid,sub['id'],billing.mode))
    if status:
        db.execute('UPDATE billing_cancellations SET status=?,ends=? WHERE user_id=? AND subscription=? AND mode=?',(status,ends or 0,uid,sub['id'],billing.mode))
        if not db.execute('SELECT 1 FROM billing_cancellations WHERE user_id=? AND subscription=? AND mode=?',(uid,sub['id'],billing.mode)).fetchone():
            db.execute('INSERT INTO billing_cancellations VALUES(?,?,?,?,?,?,?)',(secrets.token_hex(16),uid,sub['id'],billing.mode,status,ends,time.time()))

def portal(billing,uid):
    from .billing import BillingUnavailable
    from .customer_access import require_customer_ready
    require_customer_ready(billing.store,uid)
    if not billing.portal_configuration:raise BillingUnavailable('Stripe-hosted billing management is not configured.')
    with billing.store.connection() as db:row=owned(billing,db,uid)
    verified(billing,row)
    validate_portal(billing)
    result=billing.provider.portal(row['customer'],billing.portal_configuration,billing.origin+'/?billing=return')
    url=result.get('url','')
    try:
        parsed=urlsplit(url)
        safe=parsed.scheme=='https' and parsed.hostname=='billing.stripe.com' and not parsed.username and not parsed.password and parsed.port in (None,443) and not parsed.fragment
    except ValueError:safe=False
    if not safe:raise BillingUnavailable('Invalid Stripe portal response.')
    return {'url':url,'sandbox':not billing.live}


def validate_portal(billing):
    from .billing import BillingUnavailable
    config=billing.provider.portal_config(billing.portal_configuration);features=config.get('features') or {}
    if (config.get('id')!=billing.portal_configuration or config.get('livemode') is not billing.live or config.get('active') is not True or
        (features.get('payment_method_update') or {}).get('enabled') is not True or
        (features.get('invoice_history') or {}).get('enabled') is not True or
        (features.get('subscription_cancel') or {}).get('enabled') is not True or
        (features.get('subscription_cancel') or {}).get('mode')!='immediately' or
        (features.get('subscription_cancel') or {}).get('proration_behavior')!='none' or
        (features.get('subscription_update') or {}).get('enabled') is not False or
        any(value.get('enabled') for name,value in features.items() if name not in {'payment_method_update','invoice_history','subscription_cancel','subscription_update'} and isinstance(value,dict))):
        raise BillingUnavailable('Portal must permit only payment methods, invoices, and immediate cancellation without proration.')
