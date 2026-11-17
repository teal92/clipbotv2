import time
import pytest
from server.billing import Billing, BillingUnavailable
from server.store import Store
from server.budgets import BudgetLedger, BudgetDenied
from server.scouts import limits_in
from server.publication import PublicationService, PublicationDenied
from server.worker_jobs import capture_authorized, WorkerDenied
from test_billing import Provider, event

@pytest.fixture
def payer(tmp_path):
    store=Store(tmp_path/'release.db');uid=store.create_user('payer@example.test','good-long-password','payer')
    provider=Provider();billing=Billing(store,'https://clipbot.example.test',provider,{p:'price_'+p for p in ('starter','creator','pro')})
    billing.start(uid,'starter');billing.receive(event())
    import copy
    stable=provider.subscription('sub_1')
    with store.connection() as db:period=db.execute('SELECT starts,ends FROM billing_periods WHERE user_id=?',(uid,)).fetchone()
    stable['items']['data'][0].update(current_period_start=period['starts'],current_period_end=period['ends'])
    provider.subscription=lambda id:copy.deepcopy(stable)
    return store,uid,provider,billing

def test_default_mode_and_live_release_gate(tmp_path,monkeypatch):
    store=Store(tmp_path/'gate.db')
    monkeypatch.setenv('STRIPE_SECRET_KEY','rk_live_fake');monkeypatch.setenv('STRIPE_WEBHOOK_SECRET','whsec_fake')
    for p in ('STARTER','CREATOR','PRO'):monkeypatch.setenv('STRIPE_PRICE_'+p,'price_'+p)
    assert Billing(store,'https://clipbot.example.test').mode=='test'
    monkeypatch.setenv('CLIPBOT_BILLING_MODE','live')
    assert not Billing(store,'https://clipbot.example.test').ready

def test_mode_flip_blocks_every_entitlement_boundary(payer):
    store,uid,provider,billing=payer
    store.billing_mode='live'
    assert store.coverage(uid) is None
    with store.connection() as db:
        assert limits_in(db,uid)['scouts']==0
        with pytest.raises(PublicationDenied):PublicationService.active_coverage(db,uid)
        with pytest.raises(WorkerDenied):capture_authorized(db,uid)
    with pytest.raises(BudgetDenied):BudgetLedger(store,enabled=True).reserve(uid,'review',1000)

def test_manual_allowance_cannot_become_live_paid(tmp_path):
    store=Store(tmp_path/'manual.db');uid=store.create_user('manual@example.test','good-long-password','manual')
    store.set_coverage(uid,review_daily=10,user_monthly=10000,scouts=6,favorites=6,categories=6,posts=5)
    store.billing_mode='live'
    assert store.coverage(uid) is None
    with store.connection() as db:
        assert limits_in(db,uid)['scouts']==0
        with pytest.raises(WorkerDenied):capture_authorized(db,uid)

def test_cancel_durable_unknown_response_never_reissues(payer):
    store,uid,provider,billing=payer;calls=[]
    def cancel(id,key):
        calls.append(key)
        with store.connection() as db:assert db.execute('SELECT status FROM billing_cancellations WHERE user_id=?',(uid,)).fetchone()[0]=='requested'
        raise TimeoutError('unknown result')
    provider.cancel_now=cancel
    with pytest.raises(TimeoutError):billing.cancel(uid)
    assert billing.cancel(uid)['status']=='reconciliation_required'
    assert len(calls)==1 and store.coverage(uid) is None

def test_cancel_ends_access_immediately_and_is_idempotent(payer):
    store,uid,provider,billing=payer;calls=[]
    provider.cancel_now=lambda id,key:(calls.append(key) or {**provider.subscription(id),'status':'canceled','ended_at':int(time.time())})
    result=billing.cancel(uid)
    assert result['status']=='canceled' and result['effectiveAt']<=time.time()
    assert billing.cancel(uid)==result and len(calls)==1 and store.coverage(uid) is None

def test_portal_configuration_and_url_fail_closed(payer,monkeypatch):
    store,uid,provider,billing=payer
    billing.portal_configuration='bpc_test'
    provider.portal_config=lambda id:{'id':id,'active':True,'livemode':False,'features':{'payment_method_update':{'enabled':True},'invoice_history':{'enabled':True},'subscription_cancel':{'enabled':True,'mode':'immediately','proration_behavior':'none'},'subscription_update':{'enabled':False}}}
    provider.portal=lambda customer,config,url:{'url':'https://billing.stripe.com/p/session/test'}
    assert billing.portal(uid)['url'].startswith('https://billing.stripe.com/')
    provider.portal=lambda *args:{'url':'https://billing.stripe.com.evil.test/'}
    with pytest.raises(BillingUnavailable):billing.portal(uid)
    provider.portal_config=lambda id:{'id':id,'active':True,'livemode':False,'features':{'subscription_update':{'enabled':True}}}
    with pytest.raises(BillingUnavailable):billing.portal(uid)

def test_cancellation_routes_require_auth_csrf_and_are_account_owned(payer):
    from fastapi.testclient import TestClient
    from server.app import create_app
    store,uid,provider,billing=payer
    provider.cancel_now=lambda id,key:{**provider.subscription(id),'status':'canceled','ended_at':int(time.time())}
    token,csrf=store.new_session(uid)
    with TestClient(create_app(store,origin='http://testserver',billing=billing)) as client:
        assert client.post('/api/billing/cancel',json={'acknowledged':True},headers={'Origin':'http://testserver'}).status_code==401
        client.cookies.set('clipbot_session',token)
        assert client.post('/api/billing/cancel',json={'acknowledged':True},headers={'Origin':'http://testserver'}).status_code==403
        headers={'Origin':'http://testserver','X-CSRF-Token':csrf}
        result=client.post('/api/billing/cancel',json={'acknowledged':True},headers=headers)
        assert result.status_code==200 and result.json()['status']=='canceled'
        assert client.get('/api/account').json()['billing']['cancellation']['status']=='canceled'

def test_restricted_test_key_enables_test_only(tmp_path,monkeypatch):
    monkeypatch.setenv('STRIPE_SECRET_KEY','rk_test_fake');monkeypatch.setenv('STRIPE_WEBHOOK_SECRET','whsec_fake')
    for p in ('STARTER','CREATOR','PRO'):monkeypatch.setenv('STRIPE_PRICE_'+p,'price_'+p)
    service=Billing(Store(tmp_path/'restricted.db'),'https://clipbot.example.test')
    assert service.ready and service.mode=='test'

def test_live_requires_acceptance_and_rejects_test_events(tmp_path,monkeypatch):
    monkeypatch.setenv('CLIPBOT_BILLING_MODE','live');monkeypatch.setenv('CLIPBOT_LIVE_BILLING_ACCEPTED','true')
    monkeypatch.setenv('STRIPE_SECRET_KEY','rk_live_fake');monkeypatch.setenv('STRIPE_WEBHOOK_SECRET','whsec_fake')
    monkeypatch.setenv('STRIPE_PORTAL_CONFIGURATION','bpc_live_fake')
    provider=Provider();prices={p:'price_'+p for p in ('starter','creator','pro')}
    service=Billing(Store(tmp_path/'live.db'),'https://clipbot.example.test',provider,prices)
    assert service.ready and service.mode=='live'
    with pytest.raises(BillingUnavailable):service.receive(event())

def test_webhook_reconciles_uncertain_cancellation(payer):
    store,uid,provider,billing=payer
    provider.cancel_now=lambda *args:(_ for _ in ()).throw(TimeoutError())
    with pytest.raises(TimeoutError):billing.cancel(uid)
    original=provider.subscription
    provider.subscription=lambda id:{**original(id),'status':'canceled','ended_at':int(time.time())}
    billing.receive(event('evt_cancel_reconciled'))
    assert billing.cancellation_status(uid)['status']=='canceled'


def test_live_checkout_cannot_mutate_before_portal_and_prices_validation(tmp_path,monkeypatch):
    monkeypatch.setenv('CLIPBOT_BILLING_MODE','live');monkeypatch.setenv('CLIPBOT_LIVE_BILLING_ACCEPTED','true')
    monkeypatch.setenv('STRIPE_SECRET_KEY','rk_live_fake');monkeypatch.setenv('STRIPE_WEBHOOK_SECRET','whsec_fake');monkeypatch.setenv('STRIPE_PORTAL_CONFIGURATION','bpc_live_fake')
    store=Store(tmp_path/'live-validation.db');uid=store.create_user('live@example.test','good-long-password','live_payer')
    provider=Provider();provider.live=True
    provider.portal_config=lambda id:{'id':id,'active':True,'livemode':False,'features':{}}
    service=Billing(store,'https://clipbot.example.test',provider,{p:'price_'+p for p in ('starter','creator','pro')})
    with pytest.raises(BillingUnavailable):service.start(uid,'starter')
    assert provider.calls==0

def test_cancel_rejects_scheduled_downgrade_without_mutation(payer):
    store,uid,provider,billing=payer
    original=provider.subscription;provider.subscription=lambda id:{**original(id),'schedule':'sub_sched_owned'}
    provider.cancel_now=lambda *args:pytest.fail('Schedule-controlled subscription must not be mutated')
    with pytest.raises(BillingUnavailable,match='pending plan change'):billing.cancel(uid)
    with store.connection() as db:assert not db.execute('SELECT 1 FROM billing_cancellations').fetchone()

def test_other_account_cannot_cancel_or_open_portal(payer):
    store,uid,provider,billing=payer
    other=store.create_user('other@example.test','good-long-password','other')
    provider.cancel_now=lambda *args:pytest.fail('Other account must not reach provider mutation')
    with pytest.raises(BillingUnavailable):billing.cancel(other)
    billing.portal_configuration='bpc_config'
    with pytest.raises(BillingUnavailable):billing.portal(other)

def test_cancellation_rejects_changed_paid_period(payer):
    store,uid,provider,billing=payer
    original=provider.subscription
    def renewed(id):
        result=original(id);result['items']['data'][0]['current_period_end']+=86400
        return result
    provider.subscription=renewed
    provider.cancel_now=lambda id,key:{**renewed(id),'status':'canceled','ended_at':int(time.time())}
    with pytest.raises(BillingUnavailable,match='period'):billing.cancel(uid)

def test_checkout_response_mode_is_not_cached(tmp_path):
    store=Store(tmp_path/'checkout-mode.db');uid=store.create_user('mode@example.test','good-long-password','mode_payer')
    provider=Provider()
    provider.checkout=lambda params,key:{'id':'cs_untrusted','livemode':True,'url':'https://checkout.stripe.com/c/pay/cs_untrusted'}
    billing=Billing(store,'https://clipbot.example.test',provider,{p:'price_'+p for p in ('starter','creator','pro')})
    with pytest.raises(BillingUnavailable):billing.start(uid,'starter')
    with store.connection() as db:assert db.execute('SELECT url FROM billing_requests').fetchone()[0] is None

def test_legacy_requests_are_durably_migrated_as_test(tmp_path):
    path=tmp_path/'legacy.db';store=Store(path)
    with store.connection() as db:db.execute('INSERT INTO billing_requests(id,user_id,plan,created) VALUES(?,?,?,?)',('legacy_request','legacy_user','starter',time.time()))
    migrated=Store(path)
    with migrated.connection() as db:assert db.execute("SELECT mode FROM billing_modes WHERE resource='request' AND id='legacy_request'").fetchone()['mode']=='test'

def test_cancellation_period_rollover_response_requires_reconciliation(payer):
    store,uid,provider,billing=payer
    def cancel(id,key):
        result=provider.subscription(id);result['cancel_at_period_end']=True
        result['items']['data'][0]['current_period_end']+=86400
        return result
    provider.cancel_now=cancel
    with pytest.raises(BillingUnavailable):billing.cancel(uid)
    assert billing.cancellation_status(uid)['status']=='reconciliation_required'


def test_live_plan_change_revalidates_hosted_management_before_mutation(payer,monkeypatch):
 store,uid,provider,billing=payer
 billing.mode='live';billing.live=True
 from server.billing_modes import bind_mode
 with store.connection() as db:bind_mode(db,'state',uid,'live')
 def reject_portal(service):raise BillingUnavailable('Hosted management configuration changed')
 monkeypatch.setattr('server.billing_management.validate_portal',reject_portal)
 provider.subscription=lambda *args:pytest.fail('Live preflight must reject before further provider actions')
 with pytest.raises(BillingUnavailable,match='configuration changed'):billing.change(uid,'creator')
