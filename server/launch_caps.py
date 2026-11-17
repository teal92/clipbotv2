"""Clamp existing paid allocations to approved launch safeguards without granting capacity."""
from .pricing import quote


def effective_caps(db,uid,coverage,billing,*,include_showcase=True):
    from .owner_showcase import showcase_in
    showcase=showcase_in(db,uid) if include_showcase else None
    if showcase:return showcase
    result=dict(coverage)
    result['monthly_reviews']=billing['monthly_reviews'] if billing else None
    result['daily_ai']=None
    if not billing or billing['plan'] not in ('pro','custom'):return result
    plan=billing['plan']
    custom=None
    if plan=='custom':
        from .custom_billing import config
        custom=config(db,'state',uid) if db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='billing_custom_capacity'").fetchone() else None
        if custom is None:
            result.update(review_daily=0,user_monthly=0,monthly_reviews=0,daily_ai=0)
            return result
    approved=quote(plan,custom)
    result['review_daily']=min(result['review_daily'],approved['quantities']['dailyReviews'])
    result['user_monthly']=min(result['user_monthly'],approved['aiCeilingMicros'])
    monthly=approved['monthlyReviews']
    result['monthly_reviews']=monthly if result['monthly_reviews'] is None else min(monthly,result['monthly_reviews'])
    result['daily_ai']=approved['dailyAiCeilingMicros']
    return result
