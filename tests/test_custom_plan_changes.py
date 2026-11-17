import pytest
from test_plan_changes import changes
from test_billing_lifecycle_acceptance import lifecycle
from test_custom_billing import CUSTOM
from server.billing import BillingUnavailable

@pytest.fixture
def custom_changes(changes):
    store,uid,other,p,b,clock=changes
    original=p.price
    def price(id):
        if id.startswith('price_custom_'):return {'id':id,'active':True,'product':'prod_custom','livemode':False,'currency':'usd','unit_amount':int(id.split('_')[-1]),'recurring':{'interval':'month','interval_count':1}}
        return original(id)
    p.price=price;p.product=lambda id:{'id':id,'active':True,'livemode':False}
    b.custom_product='prod_custom';b.custom_prices={str(n):'price_custom_'+str(n) for n in range(1000,8501,500)}
    return changes

def test_paid_custom_upgrade_then_standard_downgrade_preserves_capacity_until_renewal(custom_changes):
    store,uid,other,p,b,clock=custom_changes
    assert b.change(uid,'custom',CUSTOM)['status']=='applied'
    assert store.coverage(uid)['scouts']==12 and store.coverage(uid)['review_daily']==45
    assert b.change(uid,'creator')['status']=='scheduled'
    assert store.billing_status(uid)['plan']=='custom'

def test_equal_price_custom_capacity_change_waits_for_renewal(custom_changes):
    store,uid,other,p,b,clock=custom_changes
    b.change(uid,'custom',CUSTOM)
    changed={**CUSTOM,'dailyReviews':46}
    assert b.change(uid,'custom',changed)['status']=='scheduled'
    assert store.coverage(uid)['review_daily']==45
    with pytest.raises(BillingUnavailable):b.change(uid,'custom',{**CUSTOM,'dailyReviews':47})
    from test_billing_lifecycle_acceptance import event
    sub=p.subscriptions['sub_first'];item=sub['items']['data'][0];end=item['current_period_end']
    clock[0]=end+1;item['current_period_start']=end;item['current_period_end']=end+30*86400
    p.schedule=lambda id:{'id':id,'livemode':False,'status':'active','subscription':sub['id'],'current_phase':{'start_date':int(end)},'phases':[{'start_date':int(end),'items':[{'price':item['price']['id'],'quantity':1}]}]}
    b.receive(event('evt_custom_renewal'))
    assert store.coverage(uid)['review_daily']==46

@pytest.mark.parametrize('failure',['timeout','canceled'])
def test_equal_price_renewal_does_not_apply_unconfirmed_or_canceled_schedule(custom_changes,failure):
    from test_billing_lifecycle_acceptance import event
    store,uid,other,p,b,clock=custom_changes
    b.change(uid,'custom',CUSTOM)
    changed={**CUSTOM,'dailyReviews':46}
    if failure=='timeout':
        p.downgrade=lambda *args:(_ for _ in ()).throw(TimeoutError())
        with pytest.raises(TimeoutError):b.change(uid,'custom',changed)
    else:
        b.change(uid,'custom',changed)
        p.schedule=lambda id:{'id':id,'livemode':False,'status':'canceled','subscription':None,'phases':[]}
    sub=p.subscriptions['sub_first'];item=sub['items']['data'][0];end=item['current_period_end']
    sub['schedule']=None
    clock[0]=end+1;item['current_period_start']=end;item['current_period_end']=end+30*86400
    b.receive(event('evt_unconfirmed_equal_price'))
    assert store.coverage(uid)['review_daily']==45
    assert b.change_status(uid)['status']!='applied'

@pytest.mark.parametrize('altered',['completed','ownership','mode','phase','quantity'])
def test_same_price_schedule_requires_owned_mode_and_exact_phase(custom_changes,altered):
    from test_billing_lifecycle_acceptance import event
    store,uid,other,p,b,clock=custom_changes
    b.change(uid,'custom',CUSTOM)
    b.change(uid,'custom',{**CUSTOM,'dailyReviews':46})
    sub=p.subscriptions['sub_first'];item=sub['items']['data'][0];end=item['current_period_end']
    clock[0]=end+1;item['current_period_start']=end;item['current_period_end']=end+30*86400
    schedule={'id':'sub_sched_test','livemode':False,'status':'completed','subscription':None,'released_subscription':sub['id'],'phases':[{'start_date':int(end),'items':[{'price':item['price']['id'],'quantity':1}]}]}
    if altered=='ownership':schedule['released_subscription']='sub_other'
    if altered=='mode':schedule['livemode']=True
    if altered=='phase':schedule['phases'][0]['start_date']+=1
    if altered=='quantity':schedule['phases'][0]['items'][0]['quantity']=True
    p.schedule=lambda id:schedule
    sub['schedule']=None
    b.receive(event('evt_schedule_evidence'))
    assert store.coverage(uid)['review_daily']==(46 if altered=='completed' else 45)

def test_pro_to_larger_custom_plan_sets_finite_monthly_reviews_without_reset(custom_changes):
    store,uid,other,p,b,clock=custom_changes
    b.change(uid,'pro')
    maximum={'scouts':40,'streamerFavorites':25,'categoryFavorites':25,'dailyReviews':180}
    assert b.change(uid,'custom',maximum)['status']=='applied'
    with store.connection() as db:assert 3750 <= db.execute('SELECT monthly_reviews FROM billing_state WHERE user_id=?',(uid,)).fetchone()[0] <= 3752

def test_unpaid_custom_upgrade_never_grants_slider_capacity(custom_changes):
    store,uid,other,p,b,clock=custom_changes;p.pay=False
    assert b.change(uid,'custom',CUSTOM)['status']=='payment_pending'
    assert store.coverage(uid)['scouts']==6

def test_old_subscription_event_cannot_mutate_new_subscription_custom_snapshot(custom_changes):
    from server.custom_billing import bind,config
    from server.billing_modes import bind_mode
    from test_billing_lifecycle_acceptance import event
    store,uid,other,p,b,clock=custom_changes
    b.change(uid,'custom',CUSTOM)
    with store.connection() as db:
        db.execute('INSERT INTO billing_requests(id,user_id,plan,created) VALUES(?,?,?,?)',('newer_request',uid,'creator',clock[0]+1))
        bind_mode(db,'request','newer_request','test')
        db.execute("UPDATE billing_state SET subscription='sub_newer',request_id='newer_request',plan='creator' WHERE user_id=?",(uid,))
        bind(db,'state',uid,None)
    b.receive(event('evt_old_subscription'))
    assert store.billing_status(uid)['plan']=='creator'
    with store.connection() as db:assert config(db,'state',uid) is None
