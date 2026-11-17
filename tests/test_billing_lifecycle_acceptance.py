"""Isolated acceptance checks: released code, no Stripe network or customer data."""
import copy
import time
from concurrent.futures import ThreadPoolExecutor

import pytest

from server.billing import Billing, BillingUnavailable
from server.budgets import BudgetLedger, BudgetDenied
from server.pricing import quote
from server.store import Store


class SandboxProvider:
    def __init__(self):
        self.subscriptions = {}
        self.requests = []
        self.fail_next_read = False

    def price(self, price_id):
        plan = price_id.removeprefix('price_')
        return {'id': price_id, 'active': True, 'livemode': False,
                'currency': 'usd', 'unit_amount': quote(plan)['monthlyCents'],
                'recurring': {'interval': 'month', 'interval_count': 1}}

    def checkout(self, params, key):
        self.requests.append(copy.deepcopy(params))
        number = len(self.requests)
        return {'id': f'cs_test_{number}',
                'url': f'https://checkout.stripe.com/c/pay/cs_test_{number}'}

    def subscription(self, subscription_id):
        if self.fail_next_read:
            self.fail_next_read = False
            raise TimeoutError('Simulated provider timeout')
        return copy.deepcopy(self.subscriptions[subscription_id])

    def add_subscription(self, subscription_id, params, now):
        self.subscriptions[subscription_id] = {
            'id': subscription_id, 'customer': 'cus_test_only', 'livemode': False,
            'metadata': params['subscription_data']['metadata'], 'status': 'active',
            'items': {'data': [{'quantity': 1,
                'price': self.price(params['line_items'][0]['price']),
                'current_period_start': now - 10 * 86400,
                'current_period_end': now + 20 * 86400}]},
            'latest_invoice': {'status': 'paid'}, 'cancel_at_period_end': False}


@pytest.fixture
def lifecycle(tmp_path, monkeypatch):
    clock = [time.time()]
    monkeypatch.setattr('server.billing.time.time', lambda: clock[0])
    store = Store(tmp_path / 'lifecycle.db')
    uid = store.create_user('sandbox-only@example.test', 'TestOnly!Password2026', 'sandbox_payer')
    other = store.create_user('other-only@example.test', 'TestOnly!Password2026', 'other_payer')
    provider = SandboxProvider()
    billing = Billing(store, 'https://clipbot.example.test', provider,
                      {plan: 'price_' + plan for plan in ('starter', 'creator', 'pro')})
    billing.start(uid, 'starter')
    provider.add_subscription('sub_first', provider.requests[-1], clock[0])
    store.save_preferences(uid, {'usagePreset': 'busy'})
    return store, uid, other, provider, billing, clock


def event(event_id, kind='customer.subscription.updated', subscription='sub_first'):
    obj = {'id': subscription}
    if kind.startswith('checkout.'):
        obj = {'id': 'cs_test_only', 'subscription': subscription, 'payment_status': 'paid'}
    elif kind.startswith('invoice.'):
        obj = {'id': 'in_test_only', 'parent': {'subscription_details': {'subscription': subscription}}}
    return {'id': event_id, 'livemode': False, 'type': kind, 'data': {'object': obj}}


@pytest.mark.parametrize('kind', ['checkout.session.completed',
    'checkout.session.async_payment_succeeded', 'invoice.paid', 'customer.subscription.updated'])
def test_activation_uses_provider_state_and_is_account_isolated(lifecycle, kind):
    store, uid, other, provider, billing, clock = lifecycle
    assert store.coverage(uid) is None
    billing.receive(event('evt_activate', kind))
    assert store.coverage(uid)['scouts'] == 6
    assert store.coverage(other) is None
    with store.connection() as db:
        assert db.execute('SELECT COUNT(*) FROM billing_periods').fetchone()[0] == 1


def test_duplicate_parallel_deliveries_preserve_usage_once(lifecycle):
    store, uid, other, provider, billing, clock = lifecycle
    billing.receive(event('evt_activate'))
    ledger = BudgetLedger(store, enabled=True)
    ledger.reserve(uid, 'existing-review', 1000)
    ledger.settle(uid, 'existing-review', 500, 100, 10)
    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(lambda _: billing.receive(event('evt_duplicate')), range(8)))
    assert ledger.snapshot(uid)['reviewsMonth'] == 1
    assert ledger.snapshot(uid)['spentMicros'] == 500
    with store.connection() as db:
        assert db.execute("SELECT COUNT(*) FROM billing_events WHERE id='evt_duplicate'").fetchone()[0] == 1


def test_renewal_refills_only_after_verified_paid_period(lifecycle):
    store, uid, other, provider, billing, clock = lifecycle
    billing.receive(event('evt_activate'))
    ledger = BudgetLedger(store, enabled=True)
    ledger.reserve(uid, 'previous-period', 1000)
    ledger.settle(uid, 'previous-period', 500, 100, 10)
    item = provider.subscriptions['sub_first']['items']['data'][0]
    old_end = item['current_period_end']
    clock[0] = old_end + 1
    with pytest.raises(BudgetDenied):
        ledger.reserve(uid, 'unverified-renewal', 1000)
    item['current_period_start'] = old_end
    item['current_period_end'] = old_end + 30 * 86400
    billing.receive(event('evt_renewal', 'invoice.paid'))
    assert ledger.snapshot(uid)['reviewsMonth'] == 0
    assert ledger.snapshot(uid)['spentMicros'] == 0
    ledger.reserve(uid, 'new-period', 1000)
    with store.connection() as db:
        assert db.execute('SELECT COUNT(*) FROM jobs WHERE user_id=?', (uid,)).fetchone()[0] == 2


@pytest.mark.parametrize('status', ['past_due', 'unpaid', 'incomplete', 'incomplete_expired', 'canceled', 'paused'])
def test_nonpaying_states_stop_new_paid_work(lifecycle, status):
    store, uid, other, provider, billing, clock = lifecycle
    billing.receive(event('evt_activate'))
    ledger = BudgetLedger(store, enabled=True)
    ledger.reserve(uid, 'already-started', 1000)
    provider.subscriptions['sub_first']['status'] = status
    billing.receive(event('evt_failed', 'invoice.payment_failed'))
    assert store.coverage(uid) is None
    with pytest.raises(BudgetDenied):
        ledger.reserve(uid, 'new-paid-work', 1000)
    ledger.settle(uid, 'already-started', 600, 100, 10)
    assert ledger.snapshot(uid)['spentMicros'] == 600


def test_scheduled_cancellation_keeps_paid_time_then_expires(lifecycle):
    store, uid, other, provider, billing, clock = lifecycle
    sub = provider.subscriptions['sub_first']
    sub['cancel_at_period_end'] = True
    billing.receive(event('evt_scheduled_cancel'))
    assert store.coverage(uid)['scouts'] == 6
    clock[0] = sub['items']['data'][0]['current_period_end']
    assert store.coverage(uid) is None


def test_failed_payment_recovers_and_stale_failure_cannot_revoke_paid_state(lifecycle):
    store, uid, other, provider, billing, clock = lifecycle
    sub = provider.subscriptions['sub_first']
    sub['status'] = 'past_due'
    sub['latest_invoice']['status'] = 'open'
    billing.receive(event('evt_failed', 'invoice.payment_failed'))
    assert store.coverage(uid) is None
    sub['status'] = 'active'
    sub['latest_invoice']['status'] = 'paid'
    billing.receive(event('evt_recovered', 'invoice.paid'))
    billing.receive(event('evt_delayed_failure', 'invoice.payment_failed'))
    assert store.coverage(uid)['scouts'] == 6


def test_provider_timeout_can_retry_event_without_partial_entitlements(lifecycle):
    store, uid, other, provider, billing, clock = lifecycle
    provider.fail_next_read = True
    with pytest.raises(TimeoutError):
        billing.receive(event('evt_retry'))
    assert store.coverage(uid) is None
    with store.connection() as db:
        assert db.execute('SELECT COUNT(*) FROM billing_events').fetchone()[0] == 0
    billing.receive(event('evt_retry'))
    assert store.coverage(uid)['scouts'] == 6


def test_replacement_downgrade_cannot_be_overwritten_by_old_subscription(lifecycle):
    store, uid, other, provider, billing, clock = lifecycle
    billing.receive(event('evt_activate'))
    provider.subscriptions['sub_first']['status'] = 'canceled'
    billing.receive(event('evt_cancel'))
    clock[0] += 1
    billing.start(uid, 'creator')
    provider.add_subscription('sub_second', provider.requests[-1], clock[0])
    billing.receive(event('evt_creator', subscription='sub_second'))
    assert store.coverage(uid)['scouts'] == 12
    provider.subscriptions['sub_second']['status'] = 'canceled'
    billing.receive(event('evt_cancel_creator', subscription='sub_second'))
    clock[0] += 1
    billing.start(uid, 'starter')
    provider.add_subscription('sub_third', provider.requests[-1], clock[0])
    billing.receive(event('evt_starter', subscription='sub_third'))
    provider.subscriptions['sub_second']['status'] = 'active'
    billing.receive(event('evt_stale_creator', subscription='sub_second'))
    assert store.coverage(uid)['scouts'] == 6


def test_direct_price_change_is_not_an_implemented_plan_switch(lifecycle):
    store, uid, other, provider, billing, clock = lifecycle
    billing.receive(event('evt_activate'))
    provider.subscriptions['sub_first']['items']['data'][0]['price'] = provider.price('price_creator')
    billing.receive(event('evt_direct_plan_change'))
    assert store.coverage(uid) is None
    # The existing adapter deliberately binds the original verified checkout plan.
    # A customer-facing prorated plan-switch flow is still required for production.


def test_live_event_is_rejected_before_provisioning(lifecycle):
    store, uid, other, provider, billing, clock = lifecycle
    with pytest.raises(BillingUnavailable):
        billing.receive({**event('evt_live'), 'livemode': True})
    assert store.coverage(uid) is None
