"""Customer-only reporting. Account exclusions do not change accounts or entitlements."""
import os
import re

PLANS=('starter','creator','pro','custom')
DEV_EMAIL='clipbot-local-development@example.invalid'


def customer_scope():
    owner=os.getenv('CLIPBOT_ADMIN_USER_ID','').strip()
    extra=os.getenv('CLIPBOT_METRICS_EXCLUDED_USER_IDS','').strip()
    excluded=sorted(set([owner]+[x.strip() for x in extra.split(',') if x.strip()]))
    if any(uid and not re.fullmatch(r'[a-f0-9]{32}',uid) for uid in excluded):
        raise ValueError('Invalid metric account exclusion configuration')
    excluded=[uid for uid in excluded if uid]
    placeholders=','.join('?' for _ in excluded) or "''"
    # Fail closed until the service has an explicit owner identity configured.
    sql=f"WITH customer_users AS (SELECT id FROM users WHERE email!=? AND ?!='' AND id NOT IN ({placeholders})) "
    return sql,(DEV_EMAIL,owner,*excluded),bool(owner)


def plan_counts(db,sql,args,now):
    counts=dict.fromkeys(PLANS,0)
    for row in db.execute(sql+"SELECT b.plan,COUNT(*) FROM customer_users u JOIN billing_state b ON b.user_id=u.id WHERE b.status='active' AND b.expires>? GROUP BY b.plan",(*args,now)):
        if row[0] in counts:counts[row[0]]=row[1]
    return counts
