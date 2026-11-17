import pytest
from fastapi.testclient import TestClient
from test_custom_billing import custom_billing,CUSTOM
from server.app import create_app

def test_custom_checkout_requires_acknowledged_server_price_and_csrf(custom_billing):
    store,uid,p,b=custom_billing
    with TestClient(create_app(store,origin='http://testserver',billing=b)) as client:
        login=client.post('/api/auth/login',json={'email':'custom@example.com','password':'a-long-enough-password'},headers={'Origin':'http://testserver'})
        headers={'Origin':'http://testserver','X-CSRF-Token':login.json()['csrfToken']}
        for amount in [None,1,2500,3500]:
            result=client.post('/api/billing/checkout',json={'plan':'custom','custom':CUSTOM,'quotedMonthlyCents':amount},headers=headers)
            assert result.status_code==409
        assert not p.calls
        forged=client.post('/api/billing/checkout',json={'plan':'custom','custom':CUSTOM,'quotedMonthlyCents':3000},headers={'Origin':'http://testserver'})
        assert forged.status_code==403 and not p.calls

def test_quote_input_refuses_extra_keys_fractional_numbers_and_booleans(custom_billing):
    store,uid,p,b=custom_billing
    with TestClient(create_app(store,origin='http://testserver',billing=b)) as client:
        login=client.post('/api/auth/login',json={'email':'custom@example.com','password':'a-long-enough-password'},headers={'Origin':'http://testserver'})
        headers={'Origin':'http://testserver','X-CSRF-Token':login.json()['csrfToken']}
        for custom in [{**CUSTOM,'scouts':True},{**CUSTOM,'scouts':12.5},{**CUSTOM,'currency':'JPY'}]:
            result=client.post('/api/billing/quote',json={'plan':'custom','custom':custom},headers=headers)
            assert result.status_code==422
