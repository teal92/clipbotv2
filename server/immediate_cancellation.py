"""Immediate, owned cancellation; local revocation survives delayed provider replies."""
import json,math,secrets,time

def completed(billing,row,result):
    from .billing import BillingUnavailable
    if not isinstance(result,dict) or result.get('id')!=row['subscription'] or result.get('livemode') is not billing.live or result.get('customer')!=row['customer'] or result.get('metadata',{}).get('request_id')!=row['request_id'] or result.get('status')!='canceled':
        raise BillingUnavailable('Cancellation needs reconciliation before another request.')
    ended=result.get('ended_at')
    if type(ended) not in (int,float) or not math.isfinite(ended) or not 0<ended<=time.time()+300:
        raise BillingUnavailable('Cancellation end time needs reconciliation.')
    return ended

def revoke(db,uid,subscription,mode,now):
    db.execute('INSERT OR IGNORE INTO billing_access_revocations VALUES(?,?,?,?)',(uid,subscription,mode,now))
    if db.execute("SELECT 1 FROM sqlite_master WHERE name='scout_settings'").fetchone():
        setting=db.execute('SELECT data FROM scout_settings WHERE user_id=?',(uid,)).fetchone()
        if setting:
            data=json.loads(setting['data']);data['running']=False
            db.execute('UPDATE scout_settings SET data=?,revision=?,updated=? WHERE user_id=?',(json.dumps(data),secrets.token_hex(16),now,uid))

def cancel(billing,uid):
    from .billing import BillingUnavailable
    from .billing_management import owned,verified,public,cancellation_status
    # Session/CSRF and explicit acknowledgment are checked by the route. Ending
    # billing must not require accepting newly changed terms or buying access.
    with billing.store.connection() as db:
        row=owned(billing,db,uid)
        existing=db.execute('SELECT * FROM billing_cancellations WHERE user_id=? AND subscription=? AND mode=?',(uid,row['subscription'],billing.mode)).fetchone()
    # Preserve transactions accepted under the earlier paid-through cancellation policy.
    if existing:return public(existing)
    sub=verified(billing,row)
    items=(sub.get('items') or {}).get('data') or [];item=items[0] if len(items)==1 else {}
    if item.get('current_period_end',sub.get('current_period_end'))!=row['expires']:raise BillingUnavailable('The paid period changed. Refresh billing before canceling.')
    if sub.get('status') not in ('active','past_due','unpaid') or row['expires']<=time.time():raise BillingUnavailable('This subscription requires billing reconciliation.')
    from .billing_schedule_cancellation import prepare
    scheduled=prepare(billing,row,sub,item) if sub.get('schedule') else None
    request_id=secrets.token_hex(16);now=time.time()
    with billing.store.connection(atomic=True) as db:
        if dict(owned(billing,db,uid))!=dict(row):raise BillingUnavailable('Billing changed. Refresh before canceling.')
        existing=db.execute('SELECT * FROM billing_cancellations WHERE user_id=? AND subscription=? AND mode=?',(uid,row['subscription'],billing.mode)).fetchone()
        if existing:return public(existing)
        db.execute('INSERT INTO billing_cancellations VALUES(?,?,?,?,?,?,?)',(request_id,uid,row['subscription'],billing.mode,'requested',now,now))
        revoke(db,uid,row['subscription'],billing.mode,now)
    # Persist intent before the only provider mutation. A timeout never causes a retry.
    key='clipbot-cancel-now-'+billing.mode+'-'+request_id
    if scheduled:
        result=billing.provider.cancel_schedule_now(scheduled['id'],key)
        if not isinstance(result,dict) or result.get('id')!=scheduled['id'] or result.get('livemode') is not billing.live or result.get('customer')!=row['customer'] or result.get('status')!='canceled':
            raise BillingUnavailable('Schedule cancellation needs reconciliation before another request.')
        result=verified(billing,row)
    else:result=billing.provider.cancel_now(row['subscription'],key)
    ended=completed(billing,row,result)
    with billing.store.connection(atomic=True) as db:
        actual=owned(billing,db,uid)
        if actual['subscription']!=row['subscription'] or actual['customer']!=row['customer']:raise BillingUnavailable('Subscription changed; cancellation needs reconciliation.')
        db.execute("UPDATE billing_cancellations SET status='canceled',ends=? WHERE id=?",(ended,request_id))
        db.execute("UPDATE billing_state SET status='inactive' WHERE user_id=? AND subscription=?",(uid,row['subscription']))
        db.execute('DELETE FROM coverage WHERE user_id=?',(uid,))
        db.execute('DELETE FROM billing_periods WHERE user_id=?',(uid,))
        if db.execute("SELECT 1 FROM sqlite_master WHERE name='billing_changes'").fetchone():
            db.execute("UPDATE billing_changes SET state='canceled',payment_url='' WHERE user_id=? AND subscription=? AND state IN ('requested','payment_pending','scheduled') AND COALESCE((SELECT mode FROM billing_modes WHERE resource='change' AND id=billing_changes.id),'test')=?",(uid,row['subscription'],billing.mode))
    return cancellation_status(billing,uid)
