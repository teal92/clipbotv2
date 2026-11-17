import pytest
from server.pricing import quote
from test_paid_entitlement_audit import paid
from server.budgets import BudgetDenied,period


def test_approved_launch_quotes():
    pro=quote('pro')
    assert pro['quantities']['dailyReviews']==120
    assert pro['monthlyReviews']==3600
    assert pro['aiCeilingMicros']==8000000
    assert pro['dailyAiCeilingMicros']==250000
    custom=quote('custom',{'scouts':40,'streamerFavorites':25,'categoryFavorites':25,'dailyReviews':180})
    assert custom['monthlyCents']==8500 and custom['monthlyReviews']==5400
    assert custom['aiCeilingMicros']==12000000 and custom['dailyAiCeilingMicros']==400000


@pytest.mark.parametrize('plan,cap',[('pro',250000),('custom',400000)])
def test_old_coverage_cannot_bypass_new_daily_ai_caps(tmp_path,plan,cap):
    from server.custom_billing import bind,schema
    store,uid,ledger=paid(tmp_path,daily=1000000,monthly=None,ceiling=25000000)
    with store.connection() as db:
        db.execute('UPDATE billing_state SET plan=? WHERE user_id=?',(plan,uid))
        schema(db)
        if plan=='custom':bind(db,'state',uid,{'scouts':40,'streamerFavorites':25,'categoryFavorites':25,'dailyReviews':180})
    ledger.reserve(uid,'first',cap)
    ledger.settle(uid,'first',cap,1,1)
    with pytest.raises(BudgetDenied):ledger.reserve(uid,'over',1)
    assert ledger.snapshot(uid)['reviewLimit']==(120 if plan=='pro' else 180)
    assert ledger.snapshot(uid)['monthlyReviewLimit']==(3600 if plan=='pro' else 5400)


def test_pro_launch_daily_spend_is_atomic(tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    store,uid,ledger=paid(tmp_path,daily=1000000,monthly=None,ceiling=25000000)
    with store.connection() as db:db.execute("UPDATE billing_state SET plan='pro' WHERE user_id=?",(uid,))
    def claim(n):
        try:ledger.reserve(uid,'parallel-'+str(n),40000);return True
        except BudgetDenied:return False
    with ThreadPoolExecutor(max_workers=8) as pool:assert sum(pool.map(claim,range(12)))==6
    assert ledger.snapshot(uid)['reservedMicros']==240000
