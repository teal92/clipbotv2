import json
from server.store import Store
from server.custom_billing import schema,bind
from server.custom_forecast import custom_forecast


def fixture(tmp_path,monkeypatch):
    store=Store(tmp_path/'forecast.db')
    owner=store.create_user('owner@example.invalid','a-long-test-password','Owner')
    customer=store.create_user('customer@example.invalid','a-long-test-password','Customer')
    monkeypatch.setenv('CLIPBOT_ADMIN_USER_ID',owner)
    for uid in (owner,customer):
        store.set_coverage(uid,review_daily=12,user_monthly=2000000,scouts=6,favorites=0,categories=0,posts=20)
        with store.connection() as db:
            schema(db)
            db.execute('INSERT INTO billing_state VALUES(?,?,?,?,?,?,?,?)',(uid,'sub_'+uid,'cus_'+uid,'custom','active',2000,360,None))
            db.execute('INSERT INTO billing_modes VALUES(?,?,?)',('state',uid,store.billing_mode))
            bind(db,'state',uid,{'scouts':6,'streamerFavorites':0,'categoryFavorites':0,'dailyReviews':12})
    return store,owner,customer


def test_custom_forecast_uses_purchased_quote_and_excludes_owner(tmp_path,monkeypatch):
    store,owner,customer=fixture(tmp_path,monkeypatch)
    result=custom_forecast(store,now=1000)
    assert result['complete'] is True and result['customers']==1
    assert result['groups']==[{'customers':1,'monthlyPriceUSD':10,'dailyReviews':12,'monthlyReviews':360,'dailyAIUSD':.4,'monthlyAIUSD':2}]
    serialized=json.dumps(result)
    assert all(value not in serialized for value in (owner,customer,'@example.invalid','sub_','cus_','password'))


def test_missing_quote_is_unavailable_instead_of_maximum_price(tmp_path,monkeypatch):
    store,owner,customer=fixture(tmp_path,monkeypatch)
    with store.connection() as db:db.execute("DELETE FROM billing_custom_capacity WHERE resource='state' AND id=?",(customer,))
    result=custom_forecast(store,now=1000)
    assert result['complete'] is False and result['groups']==[]


def test_expired_and_other_mode_custom_plans_do_not_count(tmp_path,monkeypatch):
    store,owner,customer=fixture(tmp_path,monkeypatch)
    with store.connection() as db:db.execute("UPDATE billing_modes SET mode='live' WHERE resource='state' AND id=?",(customer,))
    assert custom_forecast(store,now=1000)['customers']==0
    assert custom_forecast(store,now=3000)['groups']==[]


def test_scheduled_downgrade_keeps_paid_price_and_lower_effective_limits(tmp_path,monkeypatch):
    store,owner,customer=fixture(tmp_path,monkeypatch)
    with store.connection() as db:
        bind(db,'state',customer,{'scouts':40,'streamerFavorites':25,'categoryFavorites':25,'dailyReviews':180})
    group=custom_forecast(store,now=1000)['groups'][0]
    assert group['monthlyPriceUSD']==85
    assert group['dailyReviews']==12 and group['monthlyReviews']==360
    assert group['monthlyAIUSD']==2


def test_cancelled_access_is_excluded_even_before_state_refresh(tmp_path,monkeypatch):
    store,owner,customer=fixture(tmp_path,monkeypatch)
    with store.connection() as db:
        db.execute('INSERT INTO billing_access_revocations VALUES(?,?,?,?)',
                   (customer,'sub_'+customer,store.billing_mode,900))
    result=custom_forecast(store,now=1000)
    assert result['complete'] is True and result['customers']==0 and result['groups']==[]
