"""Paid-cycle accounting; global and manually provisioned caps remain UTC calendar based."""
import math,time
from datetime import datetime,timezone
class BillingPeriodUnavailable(ValueError):pass

def valid_period(starts,ends,now=None):
    now=time.time() if now is None else now
    values=(starts,ends,now)
    return all(type(v) in (int,float) and math.isfinite(v) for v in values) and 0<starts<ends and ends-starts<=35*86400 and starts<=now<ends

def paid_period(db,uid,now=None,*,require_active=True):
    from .owner_showcase import showcase_in
    if showcase_in(db,uid):return None  # Complimentary owner capacity uses UTC calendar months.
    now=time.time() if now is None else now
    row=db.execute('SELECT b.subscription,b.status,b.expires,p.subscription AS period_subscription,p.starts,p.ends FROM billing_state b LEFT JOIN billing_periods p ON p.user_id=b.user_id WHERE b.user_id=?',(uid,)).fetchone()
    if row is None:return None
    if row['starts'] is None or row['subscription']!=row['period_subscription'] or row['ends']!=row['expires'] or not valid_period(row['starts'],row['ends'],now if require_active else row['starts']) or (require_active and row['status']!='active'):
        raise BillingPeriodUnavailable('Paid billing period requires reconciliation before further AI reviews.')
    return {'start':row['starts'],'end':row['ends']}

def usage_filter(uid,billing_period,calendar_month,pipeline_only=False):
    args=[uid];where='j.user_id=?'
    if billing_period:
        start,end=billing_period['start'],billing_period['end']
        start_day=datetime.fromtimestamp(start,timezone.utc).strftime('%Y-%m-%d');end_day=datetime.fromtimestamp(end,timezone.utc).strftime('%Y-%m-%d')
        where+=' AND ((t.created IS NOT NULL AND t.created>=? AND t.created<?) OR (t.created IS NULL AND j.day>=? AND j.day<=?))';args.extend((start,end,start_day,end_day))
    else:where+=' AND j.month=?';args.append(calendar_month)
    if pipeline_only:where+=" AND j.job_id LIKE 'pipeline:%'"
    return where,args

def period_usage(db,uid,billing_period,calendar_month,pipeline_only=False):
    where,args=usage_filter(uid,billing_period,calendar_month,pipeline_only)
    return dict(db.execute('SELECT COALESCE(SUM(j.spent),0) AS spent,COALESCE(SUM(j.reserved),0) AS reserved,COALESCE(SUM(j.input_tokens),0) AS inputs,COALESCE(SUM(j.output_tokens),0) AS outputs,COUNT(*) AS reviews FROM jobs j LEFT JOIN job_timestamps t ON t.user_id=j.user_id AND t.job_id=j.job_id WHERE '+where,args).fetchone())

def period_activity(db,uid,billing_period,calendar_month):
    where,args=usage_filter(uid,billing_period,calendar_month)
    return [dict(row) for row in db.execute('SELECT j.day AS day,SUM(j.input_tokens+j.output_tokens) AS tokens FROM jobs j LEFT JOIN job_timestamps t ON t.user_id=j.user_id AND t.job_id=j.job_id WHERE '+where+' GROUP BY j.day ORDER BY j.day',args)]
