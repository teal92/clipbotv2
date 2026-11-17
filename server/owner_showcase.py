"""Host-provisioned owner capacity, separate from all Stripe billing records."""
import hmac,json,os,re
from .pricing import LIMITS,quote


def showcase_in(db,uid):
    owner=os.getenv('CLIPBOT_ADMIN_USER_ID','').strip()
    if not re.fullmatch(r'[a-f0-9]{32}',owner) or not isinstance(uid,str) or not hmac.compare_digest(owner,uid):return None
    user=db.execute('SELECT email FROM users WHERE id=?',(uid,)).fetchone()
    if not user or user['email']=='clipbot-local-development@example.invalid':return None
    row=db.execute('SELECT value FROM guards WHERE key=?',('owner_showcase:'+uid,)).fetchone()
    if not row:return None
    try:grant=json.loads(row['value'])
    except (ValueError,TypeError):return None
    if not isinstance(grant,dict) or grant.get('enabled') is not True:return None
    approved=quote('custom',{key:bounds[1] for key,bounds in LIMITS.items()})
    return dict(user_id=uid,review_daily=approved['quantities']['dailyReviews'],user_monthly=approved['aiCeilingMicros'],
                scouts=approved['quantities']['scouts'],favorites=approved['quantities']['streamerFavorites'],
                categories=approved['quantities']['categoryFavorites'],posts=20,uniqueClipsDaily=None,ownerShowcase=True,
                monthly_reviews=approved['monthlyReviews'],daily_ai=approved['dailyAiCeilingMicros'])


def operational_coverage(db,uid):
    return showcase_in(db,uid) or db.execute('SELECT * FROM coverage WHERE user_id=?',(uid,)).fetchone()


def operational_billing(db,uid):
    # This projection authorizes operations only. Billing APIs keep reading the
    # actual provider-backed billing_state and never send this object to Stripe.
    grant=showcase_in(db,uid)
    if grant:return dict(plan='custom',status='active',expires=253402300799,monthly_reviews=grant['monthly_reviews'])
    return db.execute('SELECT * FROM billing_state WHERE user_id=?',(uid,)).fetchone()


def operational_cancellation_revoked(db,uid):
    from .billing_modes import cancellation_revoked
    return not showcase_in(db,uid) and cancellation_revoked(db,uid)
