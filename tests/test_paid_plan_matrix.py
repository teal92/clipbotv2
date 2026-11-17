import time
import pytest
from server.store import Store
from server.billing import Billing
from server.pricing import quote

class Provider:
 def __init__(self,plan):self.plan=plan;self.request='';self.change={}
 def price(self,id):return {'id':id,'active':True,'livemode':False,'currency':'usd','unit_amount':quote(self.plan)['monthlyCents'],'recurring':{'interval':'month','interval_count':1}}
 def checkout(self,params,key):self.request=params['metadata']['request_id'];return {'id':'cs_test_plan','url':'https://checkout.stripe.com/c/pay/cs_test_plan'}
 def subscription(self,id):
  price={**self.price('price_'+self.plan),**self.change}
  return {'id':id,'customer':'cus_test','livemode':False,'metadata':{'request_id':self.request},'status':'active','items':{'data':[{'quantity':1,'price':price,'current_period_start':time.time()-86400,'current_period_end':time.time()+86400}]},'latest_invoice':{'status':'paid'}}

def setup(tmp_path,plan):
 store=Store(tmp_path/(plan+'.db'));uid=store.create_user('payer@example.com','legacy-long-password','Payer');provider=Provider(plan)
 billing=Billing(store,'https://clipbot.example.com',provider,{p:'price_'+p for p in ('starter','creator','pro')})
 billing.start(uid,plan);return store,uid,provider,billing

def pay(b):b.receive({'id':'evt_paid','type':'customer.subscription.updated','livemode':False,'data':{'object':{'id':'sub_test'}}})

@pytest.mark.parametrize('plan,scouts,favorites,reviews,monthly,ceiling,clips',[('starter',6,0,15,450,2000000,20),('creator',12,3,45,1350,6000000,20),('pro',30,10,120,3600,8000000,None)])
def test_paid_tier_grants_exact_server_allowances(tmp_path,plan,scouts,favorites,reviews,monthly,ceiling,clips):
 store,uid,provider,billing=setup(tmp_path,plan)
 assert store.coverage(uid) is None
 pay(billing);coverage=store.coverage(uid)
 assert coverage['scouts']==scouts and coverage['favorites']==coverage['categories']==favorites
 assert coverage['review_daily']==reviews and coverage['user_monthly']==ceiling and coverage['uniqueClipsDaily']==clips
 with store.connection() as d:assert d.execute('SELECT monthly_reviews FROM billing_state WHERE user_id=?',(uid,)).fetchone()[0]==monthly

@pytest.mark.parametrize('change',[{'recurring':{'interval':'year','interval_count':1}},{'recurring':{'interval':'month','interval_count':12}},{'livemode':True}])
def test_changed_subscription_price_contract_never_grants_coverage(tmp_path,change):
 store,uid,provider,billing=setup(tmp_path,'starter');provider.change=change
 pay(billing)
 assert store.coverage(uid) is None
