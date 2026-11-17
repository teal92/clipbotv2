"""Private dashboard aggregates. Counters describe activity, not model accuracy."""
import json, math, time
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from fastapi import APIRouter, Request, Query, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from .provider_analytics import ProviderAnalytics

SELECTION_CODES = {'analysis_no_moment', 'analysis_below_threshold', 'analysis_length_settings', 'not_selected'}

def timestamp(value):
    if type(value) in (int, float) and math.isfinite(value) and value > 0:
        return value
    return None

def aggregate_dashboard(store, uid, period='week', timezone_name='UTC', now=None):
    if period not in ('day', 'week', 'month'):
        raise ValueError('Choose day, week, or month.')
    try:
        zone = ZoneInfo(timezone_name)
    except (ZoneInfoNotFoundError, ValueError):
        raise ValueError('Choose a valid timezone.') from None
    now = time.time() if now is None else now
    today = datetime.fromtimestamp(now, zone).date()
    days = {'day': 1, 'week': 7, 'month': 30}[period]
    start_day = today - timedelta(days=days-1)
    # Hourly slots on a single day, daily slots for the rolling week/month.
    keys = [f'{today.isoformat()}T{hour:02}' for hour in range(24)] if period == 'day' else [(start_day+timedelta(days=i)).isoformat() for i in range(days)]
    buckets = {key: {'key': key, 'approved': 0, 'denied': 0, 'selected': 0, 'notSelected': 0, 'failed': 0, 'posts': 0} for key in keys}
    def add(at, field):
        if timestamp(at) is None or at > now: return
        local = datetime.fromtimestamp(at, zone)
        key = local.strftime('%Y-%m-%dT%H') if period == 'day' else local.date().isoformat()
        if key in buckets: buckets[key][field] += 1
    totals = {'approved': 0, 'denied': 0, 'selected': 0, 'notSelected': 0, 'failed': 0, 'posts': 0, 'undatedReviews': 0}
    posted_days = set()
    with store.connection() as db:
        # SQL owner filters precede JSON parsing; another owner's records never enter memory.
        for row in db.execute('SELECT data FROM reviews WHERE user_id=?', (uid,)):
            review = json.loads(row['data']); decision = review.get('user_feedback', {}).get('decision')
            field = {'approve': 'approved', 'reject': 'denied'}.get(decision)
            if not field: continue
            totals[field] += 1
            if timestamp(review.get('reviewedAt')) is None: totals['undatedReviews'] += 1
            else: add(review['reviewedAt'], field)
        tables = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if 'analysis_runs' in tables:
            for row in db.execute("SELECT a.created,a.status,j.error_code,j.stage,c.id candidate FROM pipeline_jobs j JOIN analysis_runs a ON a.job_id=j.id AND a.user_id=j.user_id LEFT JOIN candidates c ON c.id=j.id AND c.user_id=j.user_id WHERE j.user_id=? AND a.status IN ('settled','invalid','unknown')", (uid,)):
                field = 'failed' if row['status'] in ('invalid','unknown') else 'selected' if row['candidate'] else 'notSelected' if row['error_code'] in SELECTION_CODES else None
                if field: totals[field]+=1; add(row['created'], field)
        if 'publications' in tables:
            for row in db.execute("SELECT receipt,updated FROM publications WHERE user_id=? AND status='published'", (uid,)):
                receipt = json.loads(row['receipt']) if row['receipt'] else {}
                at = timestamp(receipt.get('verifiedAt')) or row['updated']
                totals['posts']+=1; add(at, 'posts')
                if at <= now: posted_days.add(datetime.fromtimestamp(at, zone).date())
    # Today's unfinished day does not break yesterday's streak.
    cursor = today if today in posted_days else today-timedelta(days=1)
    streak = 0
    while cursor in posted_days: streak+=1; cursor-=timedelta(days=1)
    return {'period': period, 'timezone': timezone_name, 'generatedAt': now, 'buckets': list(buckets.values()), 'totals': totals, 'postingStreak': streak, 'streakPostedToday': today in posted_days, 'feedbackMeaning': 'Latest approval or denial per clip; activity counts are not evidence of learning improvement.', 'postingMeaning': 'Provider-confirmed ClipBot publications; cross-posts count separately.'}

class RefreshViews(BaseModel):
    model_config = ConfigDict(extra='forbid')
    accountKey: str = Field(pattern=r'^[a-f0-9]{32}$')

def build_dashboard_router(store, current, oauth):
    router = APIRouter(); analytics = ProviderAnalytics(store, oauth)
    @router.get('/api/dashboard/metrics')
    def metrics(request: Request, period: str = Query('week', pattern=r'^(day|week|month)$'), timezone: str = Query('UTC', max_length=100)):
        uid = current(request)['user_id']
        try: result = aggregate_dashboard(store, uid, period, timezone)
        except ValueError as error: raise HTTPException(422, str(error)) from None
        result['views'] = analytics.snapshot(uid)
        return result
    @router.post('/api/dashboard/views/refresh')
    def refresh(data: RefreshViews, request: Request):
        uid = current(request, True)['user_id']
        try: return analytics.refresh(uid, data.accountKey)
        except ValueError: raise HTTPException(404, 'Connected account is unavailable.') from None
    return router
