import time
import pytest
from test_billing import billing,event
from server.billing import BillingUnavailable

@pytest.mark.parametrize('status',['past_due','unpaid','paused','active','incomplete'])
def test_recoverable_subscription_never_allows_second_checkout(billing,status):
    store,uid,provider,service=billing
    service.start(uid,'starter');service.receive(event())
    with store.connection() as db:db.execute('UPDATE billing_requests SET created=?',(time.time()-48*3600,))
    provider.status=status;provider.invoice='open';service.receive(event('evt_failed'))
    with pytest.raises(BillingUnavailable):service.start(uid,'starter')
    assert provider.calls==1

@pytest.mark.parametrize('status',['canceled','incomplete_expired'])
def test_verified_terminal_subscription_can_be_replaced(billing,status):
    store,uid,provider,service=billing
    service.start(uid,'starter');service.receive(event())
    provider.status=status;service.receive(event('evt_terminal'))
    service.start(uid,'starter')
    assert provider.calls==2
