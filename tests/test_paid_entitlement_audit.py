import time
from concurrent.futures import ThreadPoolExecutor
import pytest
from fastapi.testclient import TestClient
from server.store import Store
from server.app import create_app
from server.budgets import BudgetLedger,BudgetDenied,period

def paid(tmp_path,*,daily=15,monthly=450,ceiling=2000000):
    store=Store(tmp_path/'paid.db');uid=store.create_user('paid@example.com','StrongClipBot!2026','paid_user')
    store.set_coverage(uid,review_daily=daily,user_monthly=ceiling,scouts=6,favorites=0,categories=0,posts=20)
    now=time.time();ends=now+3600
    with store.connection() as db:
        db.execute('INSERT INTO billing_state VALUES(?,?,?,?,?,?,?,?)',(uid,'sub_fake','cus_fake','starter','active',ends,monthly,'req_fake'))
        db.execute('INSERT INTO billing_periods VALUES(?,?,?,?)',(uid,'sub_fake',now-3600,ends))
    store.save_preferences(uid,{'usagePreset':'busy'})
    return store,uid,BudgetLedger(store,global_monthly=10000000,global_daily=10000000,concurrency=50,user_concurrency=50,enabled=True)

@pytest.mark.parametrize('status,expired',[('inactive',False),('active',True)])
def test_existing_reservation_cannot_bypass_revoked_or_expired_paid_coverage(tmp_path,status,expired):
    store,uid,ledger=paid(tmp_path);ledger.reserve(uid,'existing',1000)
    with store.connection() as db:db.execute('UPDATE billing_state SET status=?,expires=? WHERE user_id=?',(status,0 if expired else time.time()+3600,uid))
    with pytest.raises(BudgetDenied):ledger.reserve(uid,'existing',1000)
    with pytest.raises(BudgetDenied):ledger.reserve(uid,'new',1000)
    assert store.coverage(uid) is None

def test_coverage_projection_is_consistent_during_billing_change(tmp_path,monkeypatch):
    store,uid,ledger=paid(tmp_path);original=store.billing_status
    def change_during_read(user_id):
        with store.connection() as db:db.execute("UPDATE billing_state SET plan='pro',status='inactive' WHERE user_id=?",(uid,))
        return original(user_id)
    monkeypatch.setattr(store,'billing_status',change_during_read)
    coverage=store.coverage(uid)
    # A read may precede revocation, but it must not mix old Starter rows with Pro posting rights.
    assert coverage is None or (coverage['review_daily']==15 and coverage['uniqueClipsDaily']==20)

def test_paid_daily_review_cap_is_atomic_under_parallel_claims(tmp_path):
    store,uid,ledger=paid(tmp_path,daily=3)
    def reserve(index):
        try:ledger.reserve(uid,'job-'+str(index),1000);return True
        except BudgetDenied:return False
    with ThreadPoolExecutor(max_workers=8) as pool:assert sum(pool.map(reserve,range(12)))==3
    assert ledger.snapshot(uid)['reviewsToday']==3

def test_monthly_review_and_monthly_spend_caps_are_independent(tmp_path):
    store,uid,ledger=paid(tmp_path,monthly=2)
    day,month=period()
    with store.connection() as db:
        for i in range(2):db.execute("INSERT INTO jobs(user_id,job_id,day,month,reserved,state) VALUES(?,?,?,?,?,?)",(uid,'old-'+str(i),day,month,0,'settled'))
    with pytest.raises(BudgetDenied,match='Monthly review'):ledger.reserve(uid,'third',1)
    with store.connection() as db:db.execute('UPDATE billing_state SET monthly_reviews=450 WHERE user_id=?',(uid,));db.execute('UPDATE coverage SET user_monthly=1 WHERE user_id=?',(uid,))
    with pytest.raises(BudgetDenied,match='spending allowance'):ledger.reserve(uid,'over-spend',2)

def test_account_and_usage_api_hide_expired_allowance_without_signing_customer_out(tmp_path):
    store,uid,ledger=paid(tmp_path);app=create_app(store,origin='http://testserver',local_signup=False)
    client=TestClient(app);token,_=store.new_session(uid);client.cookies.set('clipbot_session',token)
    assert client.get('/api/account').json()['plan']['active'] is True
    with store.connection() as db:db.execute('UPDATE billing_state SET expires=0 WHERE user_id=?',(uid,))
    account=client.get('/api/account');usage=client.get('/api/usage')
    assert account.status_code==usage.status_code==200
    assert account.json()['plan']['active'] is False and account.json()['plan']['coverage'] is None
    assert usage.json()['reviewLimit']==usage.json()['spendLimitMicros']==0
    assert store.session(token)

def test_no_coverage_and_another_customers_allowance_do_not_grant_budget(tmp_path):
    store,uid,ledger=paid(tmp_path);other=store.create_user('other@example.com','StrongClipBot!2026','other_user')
    with pytest.raises(BudgetDenied,match='active paid allowance'):ledger.reserve(other,'cross-owner',1)
    assert store.coverage(other) is None

def test_settlement_remains_accountable_after_subscription_expiry(tmp_path):
    store,uid,ledger=paid(tmp_path);ledger.reserve(uid,'in-flight',1000)
    with store.connection() as db:db.execute('UPDATE billing_state SET expires=0 WHERE user_id=?',(uid,))
    ledger.settle(uid,'in-flight',900,500,100)
    assert ledger.snapshot(uid)['spentMicros']==900 and ledger.snapshot(uid)['reservedMicros']==0
    assert ledger.reserve(uid,'in-flight',1000)['state']=='settled'
    with pytest.raises(BudgetDenied):ledger.reserve(uid,'fresh',1000)

def test_authenticated_quote_and_preferences_never_activate_paid_usage(tmp_path):
    store,uid,ledger=paid(tmp_path);other=store.create_user('free@example.com','StrongClipBot!2026','free_user')
    app=create_app(store,origin='http://testserver',local_signup=False);client=TestClient(app);token,csrf=store.new_session(other);client.cookies.set('clipbot_session',token)
    headers={'Origin':'http://testserver','X-CSRF-Token':csrf}
    quote=client.post('/api/billing/quote',json={'plan':'pro'},headers=headers)
    assert quote.status_code==200 and quote.json()['active'] is False
    assert client.put('/api/davey',json={'usagePreset':'busy','focus':'balanced','avoid':'personal','approval':'review'},headers=headers).status_code==200
    assert client.get('/api/account').json()['plan']['active'] is False
    assert client.get('/api/usage').json()['spendLimitMicros']==0
    with pytest.raises(BudgetDenied):ledger.reserve(other,'cannot-spend',1)
