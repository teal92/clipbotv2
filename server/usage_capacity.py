"""Private budget truth and bounded customer rankings. Never changes allowances."""
import time
from datetime import datetime,timezone,timedelta
from .metric_scope import customer_scope,PLANS


def capacity_usage(store,ledger,now=None):
    now=time.time() if now is None else now
    date=datetime.fromtimestamp(now,timezone.utc);day=date.strftime('%Y-%m-%d');month=date.strftime('%Y-%m')
    sql,args,configured=customer_scope();top={name:[] for name in PLANS}
    with store.connection() as db:
        def totals(column,value,limit):
            row=db.execute(f'SELECT COALESCE(SUM(spent),0),COALESCE(SUM(reserved),0) FROM jobs WHERE {column}=?',(value,)).fetchone()
            return {'spentMicros':row[0],'reservedMicros':row[1],'limitMicros':limit,'period':value}
        daily=totals('day',day,ledger.global_daily);monthly=totals('month',month,ledger.global_monthly)
        # One grouped query and a window rank, returning at most twelve users.
        # Paid-cycle usage matches the ledger's timestamp/legacy-day fallback.
        cycle="(j.created>=p.starts AND j.created<p.ends OR j.created IS NULL AND j.day>=strftime('%Y-%m-%d',p.starts,'unixepoch') AND j.day<=strftime('%Y-%m-%d',p.ends,'unixepoch'))"
        period=f'(CASE WHEN p.known THEN {cycle} ELSE j.month=? END)'
        query=sql.rstrip()+''', periods AS (
          SELECT u.id,u.name,b.plan,b.monthly_reviews,c.review_daily,c.user_monthly,
                 p.starts,p.ends,
                 (p.subscription=b.subscription AND p.ends=b.expires AND p.starts>0 AND p.ends>p.starts AND p.ends-p.starts<=3024000 AND p.starts<=? AND p.ends>?) AS known
          FROM customer_users cu JOIN users u ON u.id=cu.id
          JOIN billing_state b ON b.user_id=u.id JOIN coverage c ON c.user_id=u.id
          LEFT JOIN billing_periods p ON p.user_id=u.id
          WHERE b.status='active' AND b.expires>? AND b.plan IN ('starter','creator','pro','custom')
        ), recent_jobs AS (
          SELECT j.*,t.created FROM jobs j LEFT JOIN job_timestamps t ON t.user_id=j.user_id AND t.job_id=j.job_id WHERE j.day>=?
        ), usage AS (
          SELECT p.*,
            COALESCE(SUM(CASE WHEN j.day=? THEN j.spent ELSE 0 END),0) dailySpentMicros,
            COALESCE(SUM(CASE WHEN j.day=? THEN j.reserved ELSE 0 END),0) dailyReservedMicros,
            SUM(CASE WHEN j.day=? THEN 1 ELSE 0 END) dailyReviews,
            COALESCE(SUM(CASE WHEN '''+period+''' THEN j.spent ELSE 0 END),0) monthlySpentMicros,
            COALESCE(SUM(CASE WHEN '''+period+''' THEN j.reserved ELSE 0 END),0) monthlyReservedMicros,
            SUM(CASE WHEN '''+period+''' THEN 1 ELSE 0 END) monthlyReviews
          FROM periods p LEFT JOIN recent_jobs j ON j.user_id=p.id GROUP BY p.id
        ), ranked AS (
          SELECT *,ROW_NUMBER() OVER(PARTITION BY plan ORDER BY monthlySpentMicros+monthlyReservedMicros DESC,id) ranking FROM usage
        ) SELECT * FROM ranked WHERE ranking<=3 AND monthlySpentMicros+monthlyReservedMicros>0 ORDER BY plan,ranking'''
        for row in db.execute(query,(*args,now,now,now,(date-timedelta(days=35)).strftime('%Y-%m-%d'),day,day,day,month,month,month)):
            top[row['plan']].append({'id':row['id'],'name':row['name'],
                **{k:row[k] for k in ('dailySpentMicros','dailyReservedMicros','dailyReviews','monthlySpentMicros','monthlyReservedMicros','monthlyReviews')},
                'dailyReviewLimit':row['review_daily'],'monthlyReviewLimit':row['monthly_reviews'],
                'monthlyLimitMicros':row['user_monthly'],'periodStart':row['starts'] if row['known'] else None,
                'periodEnd':row['ends'] if row['known'] else None,'periodReconciliationRequired':not bool(row['known'])})
    return {'generatedAt':now,'timezone':'UTC','daily':daily,'monthly':monthly,'topUsers':top,
            'ownerExclusionConfigured':configured,'ranking':'Current paid-cycle AI cost, including outstanding reservations; calendar-month fallback is labeled when the paid cycle is unavailable.',
            'source':'ClipBot budget ledger; service totals include owner/internal activity to match the safety stops. Other applications using the Claude account are not included.'}
