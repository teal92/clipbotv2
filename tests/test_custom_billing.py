import copy,time
import pytest
from server.store import Store
from server.billing import Billing,BillingUnavailable

CUSTOM={'scouts':12,'streamerFavorites':3,'categoryFavorites':3,'dailyReviews':45}
class CustomProvider:
    live=False
    def __init__(self):self.calls=[];self.paid=True;self.bad=False
    def product(self,id):return {'id':id,'active':True,'livemode':False}
    def price(self,id):
        amount=int(id.split('_')[-1])
        return {'id':id,'active':True,'product':'prod_custom','currency':'usd','unit_amount':amount+(1 if self.bad else 0),'livemode':False,'recurring':{'interval':'month','interval_count':1}}
    def checkout(self,params,key):
        self.calls.append((copy.deepcopy(params),key));self.request=params['metadata']['request_id'];self.price_id=params['line_items'][0]['price']
        return {'id':'cs_custom','url':'https://checkout.stripe.com/c/pay/custom','livemode':False}
    def subscription(self,id):return {'id':id,'customer':'cus_custom','livemode':False,'status':'active','metadata':{'request_id':self.request},'items':{'data':[{'quantity':1,'price':self.price(self.price_id),'current_period_start':time.time()-86400,'current_period_end':time.time()+86400}]},'latest_invoice':{'status':'paid' if self.paid else 'open'}}

@pytest.fixture
def custom_billing(tmp_path,monkeypatch):
    import json
    monkeypatch.setenv('STRIPE_CUSTOM_PRODUCT','prod_custom')
    monkeypatch.setenv('STRIPE_CUSTOM_PRICES',json.dumps({str(n):'price_'+str(n) for n in range(1000,8501,500)}))
    store=Store(tmp_path/'custom.db');uid=store.create_user('custom@example.com','a-long-enough-password','Custom')
    p=CustomProvider();b=Billing(store,'https://clipbot.example.test',p,{'starter':'price_700','creator':'price_2500','pro':'price_6000'})
    return store,uid,p,b

def event(id='evt_custom'):return {'id':id,'livemode':False,'type':'customer.subscription.updated','data':{'object':{'id':'sub_custom'}}}

def test_custom_quote_activates_exact_owned_capacity_only_after_payment(custom_billing):
    store,uid,p,b=custom_billing
    b.start(uid,'custom',CUSTOM);assert store.coverage(uid) is None
    p.paid=False;b.receive(event());assert store.coverage(uid) is None
    p.paid=True;b.receive(event('evt_paid'));c=store.coverage(uid)
    assert (c['scouts'],c['favorites'],c['categories'],c['review_daily'])==(12,3,3,45)
    with store.connection() as db:assert db.execute('SELECT monthly_reviews FROM billing_state WHERE user_id=?',(uid,)).fetchone()[0]==1350
    assert p.calls[0][0]['line_items']==[{'price':'price_3000','quantity':1}]

def test_custom_retries_reuse_quote_and_reject_changed_capacity(custom_billing):
    store,uid,p,b=custom_billing
    result=b.start(uid,'custom',CUSTOM);assert b.start(uid,'custom',CUSTOM)==result;assert len(p.calls)==1
    with pytest.raises(BillingUnavailable):b.start(uid,'custom',{**CUSTOM,'scouts':13})

@pytest.mark.parametrize('bad',[{**CUSTOM,'scouts':True},{**CUSTOM,'scouts':1.5},{**CUSTOM,'dailyReviews':181},{**CUSTOM,'monthlyCents':1}])
def test_client_cannot_supply_price_or_out_of_range_capacity(custom_billing,bad):
    store,uid,p,b=custom_billing
    with pytest.raises(BillingUnavailable):b.start(uid,'custom',bad)
    assert not p.calls and store.coverage(uid) is None

def test_custom_price_mismatch_blocks_renewal_and_never_expands_capacity(custom_billing):
    store,uid,p,b=custom_billing
    b.start(uid,'custom',CUSTOM);b.receive(event());p.bad=True;b.receive(event('evt_bad_price'))
    assert store.coverage(uid) is None

def test_custom_price_table_requires_exact_sixteen_unique_monthly_prices(custom_billing,monkeypatch):
    import json
    store,uid,p,b=custom_billing
    monkeypatch.setenv('STRIPE_CUSTOM_PRICES',json.dumps({'1000':'price_1000'}))
    rejected=Billing(store,b.origin,p,b.prices)
    with pytest.raises(BillingUnavailable):rejected.start(uid,'custom',CUSTOM)
    assert not p.calls
