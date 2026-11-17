import copy
import pytest
from server.billing import BillingUnavailable
from server.budgets import BudgetLedger
from test_plan_changes import changes
from test_billing_lifecycle_acceptance import lifecycle,event


@pytest.fixture
def scheduled(changes):
    store,uid,other,provider,billing,clock=changes
    item=provider.subscriptions['sub_first']['items']['data'][0]
    item.update(current_period_start=int(item['current_period_start']),current_period_end=int(item['current_period_end']))
    billing.receive(event('evt_integer_stripe_period'))
    billing.change(uid,'creator');billing.change(uid,'starter')
    sub=provider.subscriptions['sub_first'];item=sub['items']['data'][0]
    starts,ends=item['current_period_start'],item['current_period_end']
    schedule={'id':'sub_sched_test','livemode':False,'customer':sub['customer'],'subscription':sub['id'],'status':'active','end_behavior':'release','current_phase':{'start_date':starts,'end_date':ends},'phases':[{'start_date':starts,'end_date':ends,'items':[{'price':'price_creator','quantity':1}],'default_payment_method':'pm_synthetic'},{'start_date':ends,'end_date':ends+30*86400,'items':[{'price':'price_starter','quantity':1}]}]}
    provider.schedule=lambda id:copy.deepcopy(schedule)
    calls=[]
    def cancel_schedule_now(id,key):
        calls.append((id,key));schedule['status']='canceled'
        sub.update(status='canceled',ended_at=int(clock[0]))
        return copy.deepcopy(schedule)
    provider.cancel_schedule_now=cancel_schedule_now
    provider.cancel_now=lambda *args:pytest.fail('Cancel only the verified owned schedule')
    return store,uid,provider,billing,clock,sub,schedule,calls


def test_cancellation_overrides_owned_pending_downgrade_without_resetting_usage(scheduled):
    store,uid,provider,billing,clock,sub,schedule,calls=scheduled
    ledger=BudgetLedger(store,enabled=True);ledger.reserve(uid,'before-cancel',1000);ledger.settle(uid,'before-cancel',500,10,1)
    result=billing.cancel(uid)
    assert result['status']=='canceled' and result['effectiveAt']==int(clock[0])
    assert billing.cancel(uid)==result and len(calls)==1
    assert billing.change_status(uid)['status']=='canceled'
    assert store.coverage(uid) is None
    with store.connection() as db:assert db.execute('SELECT SUM(spent) FROM jobs WHERE user_id=?',(uid,)).fetchone()[0]==500
    billing.receive(event('evt_cancellation_duplicate'))
    assert store.coverage(uid) is None
    clock[0]=result['effectiveAt']+1;sub['status']='canceled'
    billing.receive(event('evt_cancellation_expired'))
    assert store.coverage(uid) is None


def test_cancel_after_lower_price_renewal_preserves_current_lower_plan(scheduled):
    store,uid,provider,billing,clock,sub,schedule,calls=scheduled
    item=sub['items']['data'][0];ends=item['current_period_end']
    clock[0]=ends+1;item.update(current_period_start=ends,current_period_end=ends+30*86400,price=provider.price('price_starter'))
    schedule['current_phase']={'start_date':ends,'end_date':ends+30*86400}
    billing.receive(event('evt_schedule_renewed','invoice.paid'))
    assert billing.change_status(uid)['status']=='applied'
    result=billing.cancel(uid)
    assert result['status']=='canceled' and store.coverage(uid) is None
    assert billing.change_status(uid)['status']=='applied'
    assert len(calls)==1


@pytest.mark.parametrize('change',[{'livemode':True},{'customer':'cus_foreign'},{'subscription':'sub_foreign'},{'current_phase':{'start_date':1,'end_date':2}}])
def test_unverified_schedule_cannot_be_mutated(scheduled,change):
    store,uid,provider,billing,clock,sub,schedule,calls=scheduled
    schedule.update(change)
    with pytest.raises(BillingUnavailable):billing.cancel(uid)
    assert not calls and store.coverage(uid)['scouts']==6
    with store.connection() as db:assert not db.execute('SELECT 1 FROM billing_cancellations').fetchone()


def test_unknown_schedule_result_stays_durable_and_reconciles_without_retry(scheduled):
    store,uid,provider,billing,clock,sub,schedule,calls=scheduled
    original=provider.cancel_schedule_now
    def lost(*args):
        with store.connection() as db:assert db.execute('SELECT status FROM billing_cancellations WHERE user_id=?',(uid,)).fetchone()['status']=='requested'
        original(*args);raise TimeoutError('Synthetic lost response')
    provider.cancel_schedule_now=lost
    with pytest.raises(TimeoutError):billing.cancel(uid)
    assert billing.cancel(uid)['status']=='reconciliation_required' and len(calls)==1
    billing.receive(event('evt_schedule_cancellation_confirmed'))
    assert billing.cancellation_status(uid)['status']=='canceled'
    assert billing.change_status(uid)['status']=='canceled'
    assert store.coverage(uid) is None


@pytest.mark.parametrize('items',[{'0':{'price':'price_creator','quantity':1}},[42]])
def test_malformed_schedule_items_fail_before_mutation(scheduled,items):
    store,uid,provider,billing,clock,sub,schedule,calls=scheduled
    schedule['phases'][0]['items']=items
    with pytest.raises(BillingUnavailable):billing.cancel(uid)
    assert not calls


@pytest.mark.parametrize('tamper',[{'status':'active'},{'customer':'cus_foreign'},{'livemode':True}])
def test_inconsistent_schedule_response_never_reports_cancellation_success(scheduled,tamper):
    store,uid,provider,billing,clock,sub,schedule,calls=scheduled
    original=provider.cancel_schedule_now
    def inconsistent(*args):
        result=original(*args);result.update(tamper);return result
    provider.cancel_schedule_now=inconsistent
    with pytest.raises(BillingUnavailable,match='reconciliation'):billing.cancel(uid)
    assert billing.cancel(uid)['status']=='reconciliation_required' and len(calls)==1
