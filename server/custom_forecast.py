"""Private, anonymous forecast inputs from verified purchased Custom capacities."""
import time
from .metric_scope import customer_scope
from .custom_billing import config
from .pricing import quote
from .launch_caps import effective_caps


def custom_forecast(store,now=None):
    now=time.time() if now is None else now
    sql,args,configured=customer_scope()
    result={'customers':0,'complete':configured,'groups':[],
            'generatedAt':now,'source':'Verified current Custom subscription snapshots; owner/test accounts excluded. Recurring prices, not collected revenue.'}
    with store.connection() as db:
        rows=db.execute(sql+"""SELECT b.*,c.review_daily,c.user_monthly
            FROM customer_users u JOIN billing_state b ON b.user_id=u.id
            JOIN billing_modes m ON m.resource='state' AND m.id=b.user_id AND m.mode=?
            LEFT JOIN coverage c ON c.user_id=u.id
            WHERE b.plan='custom' AND b.status='active' AND b.expires>?
            AND NOT EXISTS(SELECT 1 FROM billing_access_revocations r
                WHERE r.user_id=b.user_id AND r.subscription=b.subscription AND r.mode=m.mode)
            ORDER BY b.user_id LIMIT 1001""",(*args,store.billing_mode,now)).fetchall()
        result['customers']=len(rows)
        if len(rows)>1000:
            result['complete']=False
            return result
        available=db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='billing_custom_capacity'").fetchone()
        groups={}
        for row in rows:
            quantities=config(db,'state',row['user_id']) if available else None
            if quantities is None or row['review_daily'] is None or row['user_monthly'] is None:
                result['complete']=False
                continue
            purchased=quote('custom',quantities)
            caps=effective_caps(db,row['user_id'],dict(row),dict(row),include_showcase=False)
            values=(purchased['monthlyCents']/100,caps['review_daily'],caps['monthly_reviews'],
                    caps['daily_ai']/1000000,caps['user_monthly']/1000000)
            groups[values]=groups.get(values,0)+1
        result['groups']=[dict(zip(('monthlyPriceUSD','dailyReviews','monthlyReviews','dailyAIUSD','monthlyAIUSD'),values),customers=count)
                          for values,count in sorted(groups.items())]
    return result
