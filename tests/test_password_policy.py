import pytest
from server.store import Store
from tests.test_account_recovery import recovery, token

@pytest.mark.parametrize('password', ['shortA1!', 'lowercaseonly1!', 'UPPERCASEONLY1!', 'NoNumberHere!', 'NoSpecialHere123', ' '*12, 'A1!'+'x'*126, 'Password123!'])
def test_new_password_policy_rejects_weak_passwords(password):
    from server.password_policy import validate_new_password
    with pytest.raises(ValueError): validate_new_password(password)

@pytest.mark.parametrize('password', ['StrongClipBot!2026', 'Correct Horse!Battery7', 'A1!'+'x'*125])
def test_new_password_policy_accepts_usable_passwords(password):
    from server.password_policy import validate_new_password
    assert validate_new_password(password) is None

def test_recovery_rejects_weak_password_without_spending_token(tmp_path):
    store,uid,service,sent=recovery(tmp_path)
    service.request_reset(uid);secret=token(sent)
    assert not service.redeem(secret,'weak-password-123')
    assert store.authenticate('customer@example.com','old-long-password')==uid
    assert service.redeem(secret,'StrongClipBot!2026')
    assert store.authenticate('customer@example.com','StrongClipBot!2026')==uid

def test_reset_api_reports_password_rules_then_redeems_same_token(tmp_path):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from server.account_recovery import build_recovery_router
    store,uid,service,sent=recovery(tmp_path);service.request_reset(uid);secret=token(sent)
    app=FastAPI();app.include_router(build_recovery_router(service));client=TestClient(app)
    bad=client.post('/api/auth/reset-password',json={'token':secret,'newPassword':'weak-password-123'})
    assert bad.status_code==422
    assert 'uppercase' in bad.json()['detail'].lower()
    good=client.post('/api/auth/reset-password',json={'token':secret,'newPassword':'StrongClipBot!2026'})
    assert good.status_code==200
