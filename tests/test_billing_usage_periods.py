from datetime import datetime,timezone,timedelta
import pytest
from server.store import Store
from server.budgets import BudgetLedger,BudgetDenied

def stamp(y,m,d):return datetime(y,m,d,12,tzinfo=timezone.utc).timestamp()

def fixture(tmp_path,monkeypatch,now=None,monthly=450,ceiling=2000000):
    start,end=stamp(2026,10,30),stamp(2026,11,30);now=now or stamp(2026,11,29)
    monkeypatch.setattr('server.budgets.time.time',lambda:now)
    date=datetime.fromtimestamp(now,timezone.utc);monkeypatch.setattr('server.budgets.period',lambda:(date.strftime('%Y-%m-%d'),date.strftime('%Y-%m')))
    store=Store(tmp_path/'cycle.db');uid=store.create_user('paid@example.com','StrongClipBot!2026','paid_user');store.set_coverage(uid,review_daily=15,user_monthly=ceiling,scouts=6,favorites=0,categories=0,posts=20);store.save_preferences(uid,{'usagePreset':'busy'})
    with store.connection() as db:
        db.executescript('CREATE TABLE IF NOT EXISTS billing_periods(user_id TEXT PRIMARY KEY,subscription TEXT NOT NULL,starts REAL NOT NULL,ends REAL NOT NULL);CREATE TABLE IF NOT EXISTS job_timestamps(user_id TEXT NOT NULL,job_id TEXT NOT NULL,created REAL NOT NULL,PRIMARY KEY(user_id,job_id));')
        db.execute('INSERT INTO billing_state VALUES(?,?,?,?,?,?,?,?)',(uid,'sub_cycle','cus_cycle','starter','active',end,monthly,'req_cycle'))
        db.execute('INSERT INTO billing_periods VALUES(?,?,?,?)',(uid,'sub_cycle',start,end))
    return store,uid,BudgetLedger(store,global_monthly=10000000,global_daily=10000000,enabled=True),start,end

def seed(store,uid,job,created,spent=0,dated=True):
    date=datetime.fromtimestamp(created,timezone.utc)
    with store.connection() as db:
        db.execute('INSERT INTO jobs(user_id,job_id,day,month,reserved,spent,state) VALUES(?,?,?,?,?,?,?)',(uid,job,date.strftime('%Y-%m-%d'),date.strftime('%Y-%m'),0,spent,'settled'))
        if dated:db.execute('INSERT INTO job_timestamps VALUES(?,?,?)',(uid,job,created))

def test_calendar_boundary_does_not_reset_450_paid_reviews(tmp_path,monkeypatch):
    store,uid,ledger,start,end=fixture(tmp_path,monkeypatch)
    for i in range(450):seed(store,uid,'previous-'+str(i),start+(i//15)*86400)
    with pytest.raises(BudgetDenied,match='Monthly review'):ledger.reserve(uid,'451st',1)
    assert ledger.snapshot(uid)['reviewsMonth']==450

def test_calendar_boundary_does_not_reset_two_dollar_paid_budget(tmp_path,monkeypatch):
    store,uid,ledger,start,end=fixture(tmp_path,monkeypatch)
    seed(store,uid,'october',stamp(2026,10,31),1000000);seed(store,uid,'november',stamp(2026,11,28),1000000)
    with pytest.raises(BudgetDenied,match='spending allowance'):ledger.reserve(uid,'over-two-dollars',1)
    assert ledger.snapshot(uid)['spentMicros']==2000000

@pytest.mark.parametrize('change',["DELETE FROM billing_periods","UPDATE billing_periods SET subscription='different'","UPDATE billing_periods SET starts=ends","UPDATE billing_periods SET ends=ends-1"])
def test_unknown_or_mismatched_period_fails_closed(tmp_path,monkeypatch,change):
    store,uid,ledger,start,end=fixture(tmp_path,monkeypatch)
    with store.connection() as db:db.execute(change)
    with pytest.raises(BudgetDenied,match='reconciliation'):ledger.reserve(uid,'blocked',1)
    snap=ledger.snapshot(uid);assert snap['periodReconciliationRequired'] is True and snap['aiEnabled'] is False

def test_reservation_stamps_time_and_settles_into_its_original_period(tmp_path,monkeypatch):
    store,uid,ledger,start,end=fixture(tmp_path,monkeypatch,now=stamp(2026,10,31))
    ledger.reserve(uid,'late-result',1000)
    with store.connection() as db:assert db.execute('SELECT created FROM job_timestamps WHERE user_id=? AND job_id=?',(uid,'late-result')).fetchone()[0]==stamp(2026,10,31)
    monkeypatch.setattr('server.budgets.time.time',lambda:stamp(2026,11,30)+1)
    ledger.settle(uid,'late-result',900,300,50)
    with store.connection() as db:assert db.execute('SELECT created FROM job_timestamps WHERE job_id=?',('late-result',)).fetchone()[0]==stamp(2026,10,31)
    monkeypatch.setattr('server.budgets.time.time',lambda:stamp(2026,11,29))
    assert ledger.snapshot(uid)['spentMicros']==900
    assert ledger.snapshot(uid)['billingPeriod']=={'start':start,'end':end}

def test_undated_history_is_conservatively_counted_by_overlapping_day(tmp_path,monkeypatch):
    store,uid,ledger,start,end=fixture(tmp_path,monkeypatch,monthly=1)
    seed(store,uid,'unknown-time',start-3600,dated=False)
    with pytest.raises(BudgetDenied,match='Monthly review'):ledger.reserve(uid,'not-free',1)
    # A known timestamp before the paid cycle is excluded even on the same UTC day.
    with store.connection() as db:db.execute('INSERT INTO job_timestamps VALUES(?,?,?)',(uid,'unknown-time',start-3600))
    assert ledger.reserve(uid,'valid-first',1)

def test_future_paid_period_reports_reconciliation_and_denies_ai(tmp_path,monkeypatch):
    store,uid,ledger,start,end=fixture(tmp_path,monkeypatch)
    with store.connection() as db:db.execute('UPDATE billing_periods SET starts=?',(end-60,))
    with pytest.raises(BudgetDenied,match='reconciliation'):ledger.reserve(uid,'future',1)
    assert ledger.snapshot(uid)['periodReconciliationRequired'] is True
    assert ledger.snapshot(uid)['aiEnabled'] is False
