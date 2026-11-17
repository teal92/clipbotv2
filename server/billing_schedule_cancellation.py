"""Cancel only a recorded owned schedule, at its current paid boundary."""
import math,time
from .billing_modes import resource_mode


def at_period_end(sub,ends):
    return sub.get('cancel_at_period_end') is True or type(ends) in (int,float) and math.isfinite(ends) and ends>0 and type(sub.get('cancel_at')) in (int,float) and sub['cancel_at']==ends


def price_id(item):
    price=item.get('price')
    return price.get('id') if isinstance(price,dict) else price


def current_phase(schedule,starts,ends,price):
    if not isinstance(schedule,dict):return None
    phases=schedule.get('phases')
    if not isinstance(phases,list) or not 1<=len(phases)<=10:return None
    matches=[p for p in phases if isinstance(p,dict) and p.get('start_date')==starts and p.get('end_date')==ends]
    if len(matches)!=1:return None
    phase=matches[0];items=phase.get('items') or []
    if not isinstance(items,list) or len(items)!=1 or not isinstance(items[0],dict) or price_id(items[0])!=price or type(items[0].get('quantity')) is not int or items[0]['quantity']!=1:return None
    return phase


def prepare(billing,row,sub,item):
    from .billing import BillingUnavailable
    schedule_id=sub.get('schedule');starts=item.get('current_period_start');ends=item.get('current_period_end')
    if not isinstance(schedule_id,str) or not schedule_id or any(type(x) not in (int,float) or not math.isfinite(x) for x in (starts,ends)) or starts!=int(starts) or ends!=int(ends) or not 0<starts<=time.time()<ends:
        raise BillingUnavailable('Resolve the pending plan change before canceling.')
    with billing.store.connection() as db:
        exists=db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='billing_changes'").fetchone()
        change=db.execute("SELECT id FROM billing_changes WHERE user_id=? AND subscription=? AND schedule_id=? AND kind='downgrade' AND state IN ('scheduled','applied') ORDER BY created DESC,rowid DESC LIMIT 1",(row['user_id'],row['subscription'],schedule_id)).fetchone() if exists else None
        if not change or resource_mode(db,'change',change['id'])!=billing.mode:raise BillingUnavailable('Resolve the pending plan change before canceling.')
        from .custom_billing import config
        custom=config(db,'state',row['user_id'])
        if not billing.valid_price(item,row['plan'],custom if row['plan']=='custom' else None):raise BillingUnavailable('The paid plan requires reconciliation before cancellation.')
    schedule=billing.provider.schedule(schedule_id)
    if not isinstance(schedule,dict) or schedule.get('id')!=schedule_id or schedule.get('livemode') is not billing.live or schedule.get('customer')!=row['customer'] or schedule.get('subscription')!=row['subscription'] or schedule.get('status')!='active' or schedule.get('current_phase')!={'start_date':starts,'end_date':ends}:
        raise BillingUnavailable('The owned schedule requires reconciliation before cancellation.')
    phase=current_phase(schedule,starts,ends,price_id(item))
    if phase is None or any(phase.get(k) for k in ('discounts','default_tax_rates','trial_end','billing_thresholds','on_behalf_of','transfer_data','application_fee_percent')):
        raise BillingUnavailable('This schedule requires assisted cancellation.')
    preserved={k:phase[k] for k in ('collection_method','default_payment_method','automatic_tax','invoice_settings','metadata') if phase.get(k) is not None}
    params={'end_behavior':'cancel','proration_behavior':'none','phases':[{**preserved,'start_date':int(starts),'end_date':int(ends),'items':[{'price':price_id(item),'quantity':1}],'proration_behavior':'none'}]}
    return {'id':schedule_id,'starts':starts,'ends':ends,'price':price_id(item),'params':params}


def validate_result(billing,row,prepared,result):
    from .billing import BillingUnavailable
    ok=isinstance(result,dict) and result.get('id')==prepared['id'] and result.get('livemode') is billing.live and result.get('customer')==row['customer'] and result.get('subscription')==row['subscription'] and result.get('status')=='active' and result.get('end_behavior')=='cancel'
    phase=current_phase(result,prepared['starts'],prepared['ends'],prepared['price']) if ok else None
    if phase is None:raise BillingUnavailable('Schedule cancellation needs reconciliation before another request.')
    for value in result['phases']:
        if not isinstance(value,dict):raise BillingUnavailable('Schedule cancellation needs reconciliation before another request.')
        start,end=value.get('start_date'),value.get('end_date')
        if any(type(x) not in (int,float) or not math.isfinite(x) for x in (start,end)) or not 0<start<end<=prepared['ends']:
            raise BillingUnavailable('Schedule cancellation needs reconciliation before another request.')


def reconcile_plan(billing,db,uid,sub,ends):
    if not at_period_end(sub,ends) or not isinstance(sub.get('schedule'),str):return
    if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='billing_changes'").fetchone():return
    rows=db.execute("SELECT id FROM billing_changes WHERE user_id=? AND subscription=? AND schedule_id=? AND kind='downgrade' AND state='scheduled'",(uid,sub['id'],sub['schedule'])).fetchall()
    for row in rows:
        if resource_mode(db,'change',row['id'])==billing.mode:db.execute("UPDATE billing_changes SET state='canceled',payment_url='' WHERE id=?",(row['id'],))
