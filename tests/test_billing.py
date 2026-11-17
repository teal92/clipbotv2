import time,pytest
from server.store import Store
from server.billing import Billing,BillingUnavailable

class Provider:
    def __init__(self):self.calls=0;self.status='active';self.invoice='paid';self.live=False;self.subscription_requests={}
    def price(self,id):return {'id':id,'active':True,'livemode':self.live,'currency':'usd','unit_amount':700,'recurring':{'interval':'month','interval_count':1}}
    def checkout(self,params,key):
        self.calls+=1;self.request=params['metadata']['request_id']
        return {'id':f'cs_test_{self.calls}','url':f'https://checkout.stripe.com/c/pay/cs_test_{self.calls}'}
    def subscription(self,id):return {'id':id,'livemode':self.live,'metadata':{'request_id':self.subscription_requests.setdefault(id,self.request)},'customer':'cus_1','status':self.status,'items':{'data':[{'quantity':1,'price':self.price('price_starter'),'current_period_start':int(time.time()-86400),'current_period_end':int(time.time()+86400)}]},'latest_invoice':{'status':self.invoice}}

@pytest.fixture
def billing(tmp_path):
    store=Store(tmp_path/'billing.db');uid=store.create_user('billing@example.com','a-good-long-password','Billing')
    provider=Provider();service=Billing(store,'https://clipbot.example.com',provider,{'starter':'price_starter','creator':'price_creator','pro':'price_pro'})
    return store,uid,provider,service

def event(id='evt_1',kind='customer.subscription.updated'):
    return {'id':id,'livemode':False,'type':kind,'data':{'object':{'id':'sub_1'}}}

def test_checkout_idempotence_and_verified_subscription(billing):
    store,uid,provider,service=billing
    a=service.start(uid,'starter');assert service.start(uid,'starter')==a;assert provider.calls==1
    assert store.coverage(uid) is None
    service.receive(event());assert store.coverage(uid)['scouts']==6
    service.receive(event());assert len(store.report_receipts(uid))==0
    with store.connection() as db:assert db.execute('SELECT COUNT(*) FROM billing_events').fetchone()[0]==1
    provider.status='canceled';service.receive(event('evt_2'));assert store.coverage(uid) is None
    provider.status='active';provider.invoice='open';service.receive(event('evt_3'));assert store.coverage(uid) is None


def test_legitimate_stripe_checkout_fragment_is_preserved_and_reused(billing):
    store,uid,provider,service=billing
    url='https://checkout.stripe.com/c/pay/cs_test_synthetic#fidkdWxOYHwnPyd1blpp'
    def checkout(params,key):
        provider.calls+=1
        return {'id':'cs_test_synthetic','livemode':False,'url':url}
    provider.checkout=checkout
    assert service.start(uid,'starter')=={'url':url,'sandbox':True}
    assert service.start(uid,'starter')['url']==url and provider.calls==1
    assert store.coverage(uid) is None


@pytest.mark.parametrize('url',[
    'javascript:alert(1)',
    'http://checkout.stripe.com/c/pay/cs_test_x',
    'https://checkout.stripe.com.attacker.invalid/c/pay/cs_test_x',
    'https://checkout.stripe.com@attacker.invalid/c/pay/cs_test_x',
    'https://user:password@checkout.stripe.com/c/pay/cs_test_x',
    'https://checkout.stripe.com:444/c/pay/cs_test_x',
    'https://checkout.stripe.com:bad/c/pay/cs_test_x',
    'https://checko\tut.stripe.com/c/pay/cs_test_x',
    'https://checkout.stripe.com/c/pay/cs_test_x#'+'x'*4096,
    None,
])
def test_checkout_rejects_unsafe_or_unbounded_provider_urls(billing,url):
    store,uid,provider,service=billing
    provider.checkout=lambda params,key:{'id':'cs_test_x','livemode':False,'url':url}
    with pytest.raises(BillingUnavailable):service.start(uid,'starter')
    assert store.coverage(uid) is None
    with store.connection() as db:
        row=db.execute('SELECT url FROM billing_requests WHERE user_id=?',(uid,)).fetchone()
        assert not row['url']

def test_wrong_mode_price_and_untrusted_events_fail_closed(billing):
    store,uid,provider,service=billing
    provider.live=True
    with pytest.raises(BillingUnavailable):service.start(uid,'starter')
    provider.live=False;service.start(uid,'starter');provider.live=True
    with pytest.raises(BillingUnavailable):service.receive(event())
    assert store.coverage(uid) is None
    with pytest.raises(BillingUnavailable):service.receive({**event(),'livemode':True})
    with pytest.raises(BillingUnavailable):service.start(uid,'custom')

def test_expired_billing_coverage_is_not_returned(billing):
    store,uid,provider,service=billing
    service.start(uid,'starter');service.receive(event())
    with store.connection() as db:db.execute('UPDATE billing_state SET expires=0')
    assert store.coverage(uid) is None


def test_webhook_rejects_forgery_without_browser_origin(billing):
    from fastapi.testclient import TestClient
    from server.app import create_app
    store,uid,provider,service=billing
    service.secret='whsec_test_only'
    with TestClient(create_app(store,origin='http://testserver',billing=service)) as client:
        assert client.post('/api/billing/webhook',content=b'{}',headers={'Stripe-Signature':'forged'}).status_code==400
        assert store.coverage(uid) is None

def test_stripe_object_conversion_verifies_signature(billing):
    import stripe,json,hmac,hashlib
    store,uid,provider,service=billing
    service.secret='whsec_test_only';timestamp=int(time.time())
    payload=json.dumps(event()).encode()
    signature=hmac.new(service.secret.encode(),str(timestamp).encode()+b'.'+payload,hashlib.sha256).hexdigest()
    verified=service.verify(payload,f't={timestamp},v1={signature}')
    assert isinstance(verified,dict)
    assert verified['id']=='evt_1'
    with pytest.raises(BillingUnavailable):service.verify(payload,f't={timestamp-600},v1={signature}')


def test_lost_checkout_response_reuses_identical_parameters(billing):
    store,uid,provider,service=billing
    saved=[]
    def create(params,key):
        assert 'expires_at' not in params  # Let Stripe apply its supported default; retries cannot violate minimum expiry.
        saved.append((params,key))
        if len(saved)==1:raise RuntimeError('Lost response')
        return {'id':'cs_test_retry','url':'https://checkout.stripe.com/c/pay/cs_test_retry'}
    provider.checkout=create
    with pytest.raises(RuntimeError):service.start(uid,'starter')
    with store.connection() as db:db.execute('UPDATE billing_requests SET url=NULL')
    time.sleep(1.1)
    service.start(uid,'starter')
    assert saved[0]==saved[1]

def test_slow_webhook_does_not_block_health_endpoint(billing):
    import asyncio,httpx
    from server.app import create_app
    store,uid,provider,service=billing
    service.verify=lambda body,signature:event()
    def slow(event):time.sleep(0.4)
    service.receive=slow
    async def check():
        app=create_app(store,origin='http://testserver',billing=service)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://testserver') as client:
            started=time.monotonic()
            delivery=asyncio.create_task(client.post('/api/billing/webhook',content=b'{}'))
            await asyncio.sleep(0.02)
            health=await client.get('/healthz')
            assert health.status_code==200
            assert time.monotonic()-started<0.3
            assert (await delivery).status_code==200
    asyncio.run(check())


def test_payment_events_preserve_usage_and_cancellation_blocks_reservations(billing):
    from server.budgets import BudgetLedger,BudgetDenied
    store,uid,provider,service=billing
    service.start(uid,'starter');service.receive(event())
    store.save_preferences(uid,{'usagePreset':'light'})
    ledger=BudgetLedger(store,enabled=True)
    ledger.reserve(uid,'existing-job',1000)
    service.receive(event('evt_second'))
    assert ledger.snapshot(uid)['reservedMicros']==1000
    provider.status='canceled';service.receive(event('evt_cancel'))
    with pytest.raises(BudgetDenied):ledger.reserve(uid,'new-job',1000)
    assert ledger.snapshot(uid)['reservedMicros']==1000


def test_failed_webhook_logs_category_without_secret(billing,caplog):
    import stripe
    from fastapi.testclient import TestClient
    from server.app import create_app
    store,uid,provider,service=billing
    service.verify=lambda body,signature:event()
    def fail(event):raise stripe.AuthenticationError('Invalid API key: sk_test_PRIVATE_VALUE',http_status=401)
    service.receive=fail
    with TestClient(create_app(store,origin='http://testserver',billing=service)) as client:
        response=client.post('/api/billing/webhook',content=b'{}')
    assert response.status_code==503
    assert 'AuthenticationError' in caplog.text
    assert '401' in caplog.text
    assert 'PRIVATE_VALUE' not in caplog.text
    assert 'sk_test_' not in response.text


def test_checkout_logs_safe_failure_category(billing,caplog):
    import stripe
    from fastapi.testclient import TestClient
    from server.app import create_app
    store,uid,provider,service=billing
    def fail(params,key):raise stripe.InvalidRequestError('Sensitive error text sk_test_PRIVATE_VALUE',param='line_items',code='parameter_unknown',http_status=400)
    provider.checkout=fail
    token,csrf=store.new_session(uid)
    with TestClient(create_app(store,origin='http://testserver',billing=service)) as client:
        client.cookies.set('clipbot_session',token)
        response=client.post('/api/billing/checkout',json={'plan':'starter'},headers={'Origin':'http://testserver','X-CSRF-Token':csrf})
    assert response.status_code==503
    assert 'ClipBot billing checkout failed' in caplog.text
    assert 'InvalidRequestError' in caplog.text
    assert 'parameter_unknown' in caplog.text
    assert 'PRIVATE_VALUE' not in caplog.text
    assert store.coverage(uid) is None


def test_checkout_uses_dashboard_payment_methods_and_avoids_cached_rejection(billing):
    import stripe
    store,uid,provider,service=billing
    request_id='old-rejected-checkout'
    with store.connection() as db:db.execute('INSERT INTO billing_requests(id,user_id,plan,created) VALUES(?,?,?,?)',(request_id,uid,'starter',time.time()))
    calls=[]
    def create(params,key):
        if key=='clipbot-'+request_id:raise stripe.InvalidRequestError('Cached unsupported payment_method_types',param='payment_method_types')
        assert 'payment_method_types' not in params
        assert params['line_items']==[{'price':'price_starter','quantity':1}]
        calls.append((params,key))
        return {'id':'cs_test_corrected','url':'https://checkout.stripe.com/c/pay/cs_test_corrected'}
    provider.checkout=create
    result=service.start(uid,'starter')
    assert result['sandbox'] is True
    assert calls[0][1]=='clipbot-checkout-v2-'+request_id
    assert service.start(uid,'starter')==result
    assert len(calls)==1
    assert store.coverage(uid) is None

def test_canceled_subscription_allows_fresh_checkout(billing):
 store,uid,provider,service=billing
 service.start(uid,'starter');service.receive(event());old=provider.request
 provider.status='canceled';service.receive(event('evt_cancel'))
 service.start(uid,'starter')
 assert provider.calls==2 and provider.request!=old
 assert store.coverage(uid) is None
 service.start(uid,'starter');assert provider.calls==2
 # A late cancellation event from the old subscription must preserve the fresh pending checkout.
 service.receive(event('evt_cancel_again'));service.start(uid,'starter');assert provider.calls==2

def test_incomplete_subscription_does_not_replace_checkout(billing):
 store,uid,provider,service=billing
 service.start(uid,'starter');provider.status='incomplete';service.receive(event())
 with pytest.raises(BillingUnavailable):service.start(uid,'creator')
 assert provider.calls==1
