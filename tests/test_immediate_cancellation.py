import copy,time
import pytest
from test_billing_release_management import payer
from server.budgets import BudgetLedger,BudgetDenied
from server.publication import PublicationService,PublicationDenied
from server.worker_jobs import capture_authorized,WorkerDenied
from server.scouts import limits_in

def deny_all(store,uid):
    assert store.coverage(uid) is None
    with store.connection() as db:
        assert limits_in(db,uid)['scouts']==0
        with pytest.raises(PublicationDenied):PublicationService.active_coverage(db,uid)
        with pytest.raises(WorkerDenied):capture_authorized(db,uid)
    with pytest.raises(BudgetDenied):BudgetLedger(store,enabled=True).reserve(uid,'after-cancel',1000)

def test_confirmed_cancellation_ends_access_without_waiting_for_webhook(payer):
    store,uid,provider,billing=payer;calls=[]
    def cancel_now(id,key):
        calls.append(key);deny_all(store,uid)
        return {**provider.subscription(id),'status':'canceled','ended_at':int(time.time())}
    provider.cancel_now=cancel_now
    result=billing.cancel(uid)
    assert result['status']=='canceled' and result['effectiveAt']<=time.time()
    deny_all(store,uid)
    assert billing.cancel(uid)==result and len(calls)==1

def test_uncertain_cancellation_pauses_usage_without_claiming_success(payer):
    store,uid,provider,billing=payer;calls=[]
    def cancel_now(*args):calls.append(args);raise TimeoutError()
    provider.cancel_now=cancel_now
    with pytest.raises(TimeoutError):billing.cancel(uid)
    deny_all(store,uid)
    assert billing.cancel(uid)['status']=='reconciliation_required' and len(calls)==1

def test_earlier_scheduled_cancellation_is_not_retroactively_revoked(payer):
    store,uid,provider,billing=payer
    with store.connection() as db:
        row=db.execute('SELECT * FROM billing_state WHERE user_id=?',(uid,)).fetchone()
        db.execute('INSERT INTO billing_cancellations VALUES(?,?,?,?,?,?,?)',('legacy',uid,row['subscription'],'test','scheduled',row['expires'],time.time()-100))
    assert billing.cancel(uid)['status']=='scheduled'
    assert store.coverage(uid)

def test_portal_validation_requires_immediate_no_proration(payer):
    from server.billing_management import validate_portal
    from server.billing import BillingUnavailable
    store,uid,provider,billing=payer;billing.portal_configuration='bpc_test'
    config={'id':'bpc_test','active':True,'livemode':False,'features':{'payment_method_update':{'enabled':True},'invoice_history':{'enabled':True},'subscription_cancel':{'enabled':True,'mode':'immediately','proration_behavior':'none'},'subscription_update':{'enabled':False}}}
    provider.portal_config=lambda _:copy.deepcopy(config)
    validate_portal(billing)
    config['features']['subscription_cancel']['proration_behavior']='create_prorations'
    with pytest.raises(BillingUnavailable):validate_portal(billing)

def test_customer_cannot_cancel_without_explicit_strict_acknowledgment(payer):
    from fastapi.testclient import TestClient
    from server.app import create_app
    store,uid,provider,billing=payer
    provider.cancel_now=lambda *args:pytest.fail('Unconfirmed request reached Stripe')
    token,csrf=store.new_session(uid)
    with TestClient(create_app(store,origin='http://testserver',billing=billing)) as client:
        client.cookies.set('clipbot_session',token)
        headers={'Origin':'http://testserver','X-CSRF-Token':csrf}
        for body in ({},{'acknowledged':False},{'acknowledged':'true'},{'acknowledged':1},{'acknowledged':True,'refund':True}):
            assert client.post('/api/billing/cancel',headers=headers,json=body).status_code==422
    assert store.coverage(uid)

def test_provider_parameters_never_invoice_prorate_or_refund():
    from server.billing import StripeProvider
    from types import SimpleNamespace
    calls=[]
    def cancel(id,params,options):calls.append((id,params,options));return SimpleNamespace(to_dict=lambda:{'status':'canceled'})
    provider=StripeProvider('rk_test_synthetic')
    provider.client=SimpleNamespace(v1=SimpleNamespace(subscriptions=SimpleNamespace(cancel=cancel),subscription_schedules=SimpleNamespace(cancel=cancel)))
    provider.cancel_now('sub_owned','one');provider.cancel_schedule_now('sub_sched_owned','two')
    assert len(calls)==2
    assert all(params=={'invoice_now':False,'prorate':False} for _,params,_ in calls)

def test_pending_upgrade_payment_does_not_prevent_cancellation(payer):
    store,uid,provider,billing=payer;original=provider.subscription
    provider.subscription=lambda id:{**original(id),'pending_update':{'expires_at':time.time()+1000}}
    provider.cancel_now=lambda id,key:{**provider.subscription(id),'status':'canceled','ended_at':int(time.time())}
    assert billing.cancel(uid)['status']=='canceled'
    deny_all(store,uid)
