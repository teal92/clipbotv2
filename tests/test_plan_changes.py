import copy
import pytest
from server.budgets import BudgetLedger
from server.billing import BillingUnavailable
from test_billing_lifecycle_acceptance import lifecycle, event, SandboxProvider


@pytest.fixture
def changes(lifecycle):
    store, uid, other, provider, billing, clock = lifecycle
    sub = provider.subscriptions['sub_first']
    sub['collection_method'] = 'charge_automatically'
    sub['items']['data'][0]['id'] = 'si_test'
    provider.change_calls = []
    provider.pay = True
    provider.schedules = {}

    def upgrade(sub_id, params, key):
        provider.change_calls.append((sub_id, copy.deepcopy(params), key))
        assert params['payment_behavior'] == 'pending_if_incomplete'
        assert params['proration_behavior'] == 'always_invoice'
        # Current Stripe API/SDK requires the typed anchor object.
        assert params['billing_cycle_anchor'] == {'type':'unchanged'}
        if provider.pay:
            sub['items']['data'][0]['price'] = provider.price(params['items'][0]['price'])
            sub['latest_invoice'] = {'id': 'in_upgrade', 'status': 'paid', 'amount_paid': 1200}
            sub['pending_update'] = None
        else:
            sub['pending_update'] = {'expires_at': clock[0] + 3600}
            sub['latest_invoice'] = {'id': 'in_upgrade', 'status': 'open', 'hosted_invoice_url': 'https://invoice.stripe.com/i/test_only'}
        return copy.deepcopy(sub)

    def downgrade(sub_id, old_price, new_price, starts, ends, key):
        provider.change_calls.append((sub_id, old_price, new_price, starts, ends, key))
        sub['schedule'] = 'sub_sched_test'
        return {'id': 'sub_sched_test', 'subscription': sub_id, 'livemode': False}

    provider.upgrade = upgrade
    provider.downgrade = downgrade
    billing.receive(event('evt_activate'))
    return lifecycle


def test_paid_upgrade_prorates_allowance_without_resetting_usage(changes):
    store, uid, other, provider, billing, clock = changes
    ledger = BudgetLedger(store, enabled=True)
    ledger.reserve(uid, 'used', 1000); ledger.settle(uid, 'used', 500, 10, 1)
    result = billing.change(uid, 'creator')
    assert result['status'] == 'applied'
    coverage = store.coverage(uid)
    assert coverage['scouts'] == 12
    assert 4600000 <= coverage['user_monthly'] <= 4700000
    assert ledger.snapshot(uid)['reviewsMonth'] == 1
    assert ledger.snapshot(uid)['spentMicros'] == 500
    assert ledger.snapshot(uid)['monthlyReviewLimit'] == 1050
    billing.receive(event('evt_upgrade_again'))
    assert store.coverage(uid)['user_monthly'] == coverage['user_monthly']
    assert len(provider.change_calls) == 1


def test_failed_upgrade_keeps_original_paid_access_and_can_confirm_later(changes):
    store, uid, other, provider, billing, clock = changes
    provider.pay = False
    result = billing.change(uid, 'creator')
    assert result['status'] == 'payment_pending'
    assert result['paymentUrl'].startswith('https://invoice.stripe.com/')
    assert store.coverage(uid)['scouts'] == 6
    assert billing.change(uid, 'creator')['id'] == result['id']
    assert len(provider.change_calls) == 1
    with pytest.raises(BillingUnavailable): billing.change(uid, 'pro')
    sub = provider.subscriptions['sub_first']
    sub['items']['data'][0]['price'] = provider.price('price_creator')
    sub['pending_update'] = None; sub['latest_invoice']['status'] = 'paid'
    billing.receive(event('evt_upgrade_paid', 'invoice.paid'))
    assert store.coverage(uid)['scouts'] == 12
    assert billing.change_status(uid)['status'] == 'applied'


def test_unpaid_changed_price_never_receives_upgrade_limits(changes):
    store, uid, other, provider, billing, clock = changes
    provider.pay = False; billing.change(uid, 'creator')
    sub = provider.subscriptions['sub_first']
    sub['items']['data'][0]['price'] = provider.price('price_creator')
    sub['pending_update'] = None
    billing.receive(event('evt_unpaid'))
    assert store.coverage(uid) is None


def test_downgrade_limits_apply_now_and_price_waits_for_next_paid_period(changes):
    store, uid, other, provider, billing, clock = changes
    billing.change(uid, 'creator')
    result = billing.change(uid, 'starter')
    assert result['status'] == 'scheduled'
    assert store.coverage(uid)['scouts'] == 6
    assert store.billing_status(uid)['plan'] == 'creator'
    assert BudgetLedger(store).snapshot(uid)['monthlyReviewLimit'] == 450
    billing.receive(event('evt_duplicate_old_paid_price'))
    assert store.coverage(uid)['scouts'] == 6
    assert store.coverage(uid)['user_monthly'] == 2000000
    assert len(provider.change_calls) == 2
    assert billing.change(uid, 'starter')['id'] == result['id']
    sub = provider.subscriptions['sub_first']; item = sub['items']['data'][0]
    end = item['current_period_end']
    item['price'] = provider.price('price_starter')
    billing.receive(event('evt_early_downgrade'))
    assert store.coverage(uid) is None
    clock[0] = end + 1
    item['current_period_start'] = end; item['current_period_end'] = end + 30 * 86400
    sub['latest_invoice']['status'] = 'paid'
    billing.receive(event('evt_renewed', 'invoice.paid'))
    assert store.coverage(uid)['scouts'] == 6
    assert store.coverage(uid)['user_monthly'] == 2000000
    assert billing.change_status(uid)['status'] == 'applied'


def test_downgrade_timeout_does_not_reduce_capacity(changes):
    store, uid, other, provider, billing, clock = changes
    billing.change(uid, 'pro')
    provider.downgrade = lambda *args: (_ for _ in ()).throw(TimeoutError())
    with pytest.raises(TimeoutError): billing.change(uid, 'starter')
    assert store.coverage(uid)['scouts'] == 30
    assert store.coverage(uid)['uniqueClipsDaily'] is None


def test_downgrade_caps_posting_and_preserves_usage(changes):
    store, uid, other, provider, billing, clock = changes
    billing.change(uid, 'pro')
    ledger = BudgetLedger(store, enabled=True)
    ledger.reserve(uid, 'prior', 1000); ledger.settle(uid, 'prior', 500, 10, 1)
    billing.change(uid, 'starter')
    assert store.coverage(uid)['uniqueClipsDaily'] == 20
    assert store.coverage(uid)['favorites'] == 0
    assert ledger.snapshot(uid)['reviewsMonth'] == 1
    assert ledger.snapshot(uid)['spentMicros'] == 500


def test_upgrade_full_allowance_only_at_renewal(changes):
    store, uid, other, provider, billing, clock = changes
    billing.change(uid, 'creator')
    sub = provider.subscriptions['sub_first']; item = sub['items']['data'][0]
    end = item['current_period_end']; clock[0] = end + 1
    item['current_period_start'] = end; item['current_period_end'] = end + 30 * 86400
    billing.receive(event('evt_next_period', 'invoice.paid'))
    assert store.coverage(uid)['user_monthly'] == 6000000
    assert BudgetLedger(store).snapshot(uid)['monthlyReviewLimit'] == 1350


def test_plan_change_requires_owned_active_subscription_and_known_price(changes):
    store, uid, other, provider, billing, clock = changes
    with pytest.raises(BillingUnavailable): billing.change(other, 'creator')
    with pytest.raises(BillingUnavailable): billing.change(uid, 'custom')
    provider.subscriptions['sub_first']['customer'] = 'cus_someone_else'
    with pytest.raises(BillingUnavailable): billing.change(uid, 'creator')
    assert provider.change_calls == []


def test_provider_timeout_reuses_same_operation_key(changes):
    store, uid, other, provider, billing, clock = changes
    original = provider.upgrade
    calls = []
    def uncertain(sub, params, key):
        calls.append((params, key))
        if len(calls) == 1: raise TimeoutError('Simulated lost request')
        return original(sub, params, key)
    provider.upgrade = uncertain
    with pytest.raises(TimeoutError): billing.change(uid, 'creator')
    assert store.coverage(uid)['scouts'] == 6
    assert billing.change(uid, 'creator')['status'] == 'applied'
    assert calls[0] == calls[1]


def test_sequential_upgrade_preserves_prorated_budget(changes):
    store, uid, other, provider, billing, clock = changes
    billing.change(uid, 'creator'); billing.change(uid, 'pro')
    # Each of the two prorated increments rounds down to whole micro-dollars.
    assert 5999998 <= store.coverage(uid)['user_monthly'] <= 6100000
    assert store.coverage(uid)['scouts'] == 30


def test_expired_unpaid_upgrade_retains_paid_plan_and_allows_new_request(changes):
    store, uid, other, provider, billing, clock = changes
    provider.pay = False
    first = billing.change(uid, 'creator')
    sub = provider.subscriptions['sub_first']
    sub['pending_update'] = None; sub['latest_invoice']['status'] = 'void'
    billing.receive(event('evt_upgrade_expired','customer.subscription.pending_update_expired'))
    assert billing.change_status(uid)['status'] == 'expired'
    assert store.coverage(uid)['scouts'] == 6
    billing.receive(event('evt_later_unchanged'))
    assert store.coverage(uid)['scouts'] == 6
    provider.pay = True
    assert billing.change(uid, 'creator')['id'] != first['id']
    assert store.coverage(uid)['scouts'] == 12


def test_canceled_downgrade_keeps_current_plan_and_clears_pending_state(changes):
    store, uid, other, provider, billing, clock = changes
    billing.change(uid, 'creator'); billing.change(uid, 'starter')
    provider.subscriptions['sub_first']['schedule'] = None
    billing.receive(event('evt_schedule_released'))
    assert billing.change_status(uid)['status'] == 'canceled'
    assert store.coverage(uid)['scouts'] == 12
    assert billing.change(uid, 'starter')['status'] == 'scheduled'


@pytest.mark.parametrize('paid_target',[True,False])
def test_delayed_upgrade_reconciliation_after_renewal(changes,paid_target):
    store, uid, other, provider, billing, clock = changes
    provider.pay=False;billing.change(uid,'creator')
    sub=provider.subscriptions['sub_first'];item=sub['items']['data'][0]
    end=item['current_period_end'];clock[0]=end+1
    item['current_period_start']=end;item['current_period_end']=end+30*86400
    sub['pending_update']=None;sub['latest_invoice']['status']='paid'
    if paid_target:item['price']=provider.price('price_creator')
    billing.receive(event('evt_late_renewal','invoice.paid'))
    assert store.coverage(uid)['scouts']==(12 if paid_target else 6)
    assert store.coverage(uid)['user_monthly']==(6000000 if paid_target else 2000000)
    assert billing.change_status(uid)['status']==('applied' if paid_target else 'expired')


def test_old_pending_change_cannot_block_replacement_subscription(changes):
    store, uid, other, provider, billing, clock = changes
    provider.pay=False;billing.change(uid,'creator')
    sub=provider.subscriptions['sub_first'];sub['status']='canceled'
    billing.receive(event('evt_cancel_during_upgrade'))
    clock[0]+=1;billing.start(uid,'pro')
    provider.add_subscription('sub_replacement',provider.requests[-1],clock[0])
    replacement=provider.subscriptions['sub_replacement']
    replacement['collection_method']='charge_automatically';replacement['items']['data'][0]['id']='si_replacement'
    billing.receive(event('evt_replacement',subscription='sub_replacement'))
    assert billing.change_status(uid) is None
    # Scheduling a replacement downgrade must not invoke the canceled subscription's upgrade.
    def replacement_schedule(sub_id,*args):
        replacement['schedule']='sched_replacement'
        return {'id':'sched_replacement','subscription':sub_id,'livemode':False}
    provider.downgrade=replacement_schedule
    assert billing.change(uid,'starter')['status']=='scheduled'


def test_stripe_adapter_updates_same_item_and_preserves_schedule_settings():
    from types import SimpleNamespace
    from server.billing import StripeProvider
    calls=[]
    class Result:
        def __init__(self,data):self.data=data
        def to_dict(self):return self.data
    class Schedules:
        def create(self,params,options):
            calls.append(('create',params,options))
            return Result({'id':'sched_test','subscription':'sub_test','livemode':False,'phases':[{'start_date':100,'end_date':200,'items':[{'price':'price_creator','quantity':1}],'metadata':{'request_id':'req_test'},'default_payment_method':'pm_test'}]})
        def update(self,id,params,options):
            calls.append(('update',id,params,options))
            return Result({'id':id,'subscription':'sub_test','livemode':False})
    provider=StripeProvider.__new__(StripeProvider)
    provider.client=SimpleNamespace(v1=SimpleNamespace(subscription_schedules=Schedules()))
    provider.downgrade('sub_test','price_creator','price_starter',100,200,'stable_key')
    phases=calls[1][2]['phases']
    assert phases[0]['items']==[{'price':'price_creator','quantity':1}]
    assert phases[1]['items']==[{'price':'price_starter','quantity':1}]
    assert phases[1]['start_date']==200 and phases[1]['proration_behavior']=='none'
    assert all(p['metadata']=={'request_id':'req_test'} and p['default_payment_method']=='pm_test' for p in phases)
    assert calls[0][2]['idempotency_key']=='stable_key-create'
    assert calls[1][3]['idempotency_key']=='stable_key-schedule'


def test_plan_change_api_requires_login_csrf_and_rejects_other_account_id(changes):
    from fastapi.testclient import TestClient
    from server.app import create_app
    store, uid, other, provider, billing, clock = changes
    token, csrf = store.new_session(uid)
    with TestClient(create_app(store, origin='http://testserver', billing=billing)) as client:
        assert client.post('/api/billing/change', json={'plan':'creator'}).status_code in (401,403)
        client.cookies.set('clipbot_session', token)
        assert client.post('/api/billing/change', json={'plan':'creator'}).status_code == 403
        headers = {'Origin':'http://testserver', 'X-CSRF-Token':csrf}
        assert client.post('/api/billing/change', json={'plan':'creator','userId':other}, headers=headers).status_code == 422
        response = client.post('/api/billing/change', json={'plan':'creator'}, headers=headers)
        assert response.status_code == 200 and response.json()['status'] == 'applied'
        assert client.get('/api/billing/change').json()['status'] == 'applied'
