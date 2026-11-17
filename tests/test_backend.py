from server.legal import POLICY_VERSION
import pytest
from fastapi.testclient import TestClient
from concurrent.futures import ThreadPoolExecutor
from server.app import create_app
from server.store import Store
from server.budgets import BudgetLedger, BudgetDenied

@pytest.fixture
def service(tmp_path):
    store=Store(tmp_path/'test.db')
    return store, create_app(store, origin='http://testserver', local_signup=True)

def signup(client,email='one@example.com'):
    return client.post('/api/auth/signup',json={'email':email,'password':'StrongClipBot!2026','name':email.split('@')[0],'termsVersion':POLICY_VERSION},headers={'Origin':'http://testserver'})

def headers(client):
    return {'Origin':'http://testserver','X-CSRF-Token':client.get('/api/account').json()['csrfToken']}

def test_real_account_without_entitlement_and_logout(service):
    store,app=service
    with TestClient(app,client=('127.0.0.1',50000)) as client:
        assert client.get('/api/account').status_code==401
        assert signup(client).status_code==201
        assert 'HttpOnly' in client.cookies.__repr__() or client.cookies.get('clipbot_session')
        account=client.get('/api/account').json()
        assert account['user']['email']=='one@example.com'
        assert account['plan']['active'] is False
        assert client.get('/api/usage').json()['inputTokens']==0
        assert client.post('/api/auth/logout',headers=headers(client)).status_code==200
        assert client.get('/api/account').status_code==401
        assert client.post('/api/auth/login',json={'email':'one@example.com','password':'wrong-password-long'},headers={'Origin':'http://testserver'}).status_code==401
        assert client.post('/api/auth/login',json={'email':'one@example.com','password':'StrongClipBot!2026'},headers={'Origin':'http://testserver'}).status_code==200

def test_csrf_and_account_isolation(service):
    store,app=service
    with TestClient(app,client=('127.0.0.1',50000)) as a,TestClient(app,client=('127.0.0.1',50000)) as b:
        signup(a);signup(b,'two@example.com')
        assert a.put('/api/davey',json={'usagePreset':'light','focus':'humor','avoid':'personal'},headers={'Origin':'http://evil.test'}).status_code==403
        assert a.put('/api/davey',json={'usagePreset':'light','focus':'humor','avoid':'personal'},headers=headers(a)).status_code==200
        assert b.get('/api/workspace').json()['preferences']['focus']=='balanced'
        assert a.get('/api/workspace').json()['preferences']['focus']=='humor'
        assert a.post('/api/billing/checkout',json={'quantity':999},headers=headers(a)).status_code==422
        assert a.get('/api/account').json()['plan']['active'] is False

def test_public_signup_disabled_until_launch_gates(service):
    store,_=service
    with TestClient(create_app(store,origin='http://testserver',local_signup=False),client=('127.0.0.1',50000)) as client:
        assert signup(client).status_code==503

def test_atomic_global_and_user_spend_stops(tmp_path):
    store=Store(tmp_path/'budget.db')
    uid=store.create_user('budget@example.com','StrongClipBot!2026','Budget')
    ledger=BudgetLedger(store,global_monthly=10000,global_daily=10000,concurrency=20,user_concurrency=20,enabled=True)
    store.set_coverage(uid,review_daily=120,user_monthly=100000,scouts=40,favorites=25,categories=25,posts=10)
    store.save_preferences(uid,{'usagePreset':'busy'})
    def attempt(n):
        try: return ledger.reserve(uid,str(n),3000)
        except BudgetDenied:return None
    with ThreadPoolExecutor(max_workers=10) as pool:
        jobs=list(pool.map(attempt,range(10)))
    assert len([job for job in jobs if job])==3
    first=next(index for index,job in enumerate(jobs) if job)
    assert ledger.reserve(uid,str(first),3000)==jobs[first]
    assert ledger.snapshot(uid)['reservedMicros']==9000
    ledger.settle(uid,str(first),2000,100,10)
    assert ledger.snapshot(uid)['spentMicros']==2000
    assert ledger.snapshot(uid)['inputTokens']==100
    with pytest.raises(BudgetDenied):ledger.reserve(uid,'extra',3000)

def test_kill_switch_no_plan_and_duplicate_settlement(tmp_path):
    store=Store(tmp_path/'budget.db');uid=store.create_user('u@example.com','StrongClipBot!2026','U')
    ledger=BudgetLedger(store,enabled=False)
    with pytest.raises(BudgetDenied):ledger.reserve(uid,'x',3000)
    ledger.enabled=True
    with pytest.raises(BudgetDenied):ledger.reserve(uid,'x',3000)
    store.set_coverage(uid,review_daily=1,user_monthly=3000,scouts=1,favorites=0,categories=0,posts=1)
    store.save_preferences(uid,{'usagePreset':'busy'})
    ledger.reserve(uid,'x',3000);ledger.settle(uid,'x',3000,20,2);ledger.settle(uid,'x',3000,20,2)
    assert ledger.snapshot(uid)['spentMicros']==3000
    with pytest.raises(BudgetDenied):ledger.reserve(uid,'y',1)
def test_paused_preset_and_daily_budget_are_enforced(tmp_path):
    store=Store(tmp_path/'preset.db');uid=store.create_user('p@example.com','StrongClipBot!2026','P')
    store.set_coverage(uid,review_daily=120,user_monthly=25_000_000,scouts=40,favorites=25,categories=25,posts=10)
    ledger=BudgetLedger(store,enabled=True)
    with pytest.raises(BudgetDenied):ledger.reserve(uid,'paused',3000)
    store.save_preferences(uid,{'usagePreset':'light','focus':'balanced','avoid':'personal','approval':'review'})
    ledger.reserve(uid,'first',250000);ledger.settle(uid,'first',250000,10,1)
    with pytest.raises(BudgetDenied):ledger.reserve(uid,'second',1)

def test_auto_throttle_at_eighty_percent(tmp_path):
    store=Store(tmp_path/'throttle.db');uid=store.create_user('t@example.com','StrongClipBot!2026','T')
    store.set_coverage(uid,review_daily=120,user_monthly=1000000,scouts=1,favorites=0,categories=0,posts=1)
    store.save_preferences(uid,{'usagePreset':'busy','focus':'balanced','avoid':'personal','approval':'review'})
    ledger=BudgetLedger(store,global_monthly=10000,global_daily=10000,user_concurrency=10,enabled=True)
    ledger.reserve(uid,'large',8000);ledger.settle(uid,'large',8000,10,1)
    ledger.reserve(uid,'one',100)
    with pytest.raises(BudgetDenied):ledger.reserve(uid,'two',100)


def test_remote_peer_cannot_use_local_signup(service):
    store,app=service
    with TestClient(app,client=('203.0.113.10',50000)) as client:
        assert signup(client).status_code==503

def test_provider_overrun_persists_stop_across_ledger_restart(tmp_path):
    store=Store(tmp_path/'overrun.db');uid=store.create_user('o@example.com','StrongClipBot!2026','O')
    store.set_coverage(uid,review_daily=120,user_monthly=1000000,scouts=1,favorites=0,categories=0,posts=1)
    store.save_preferences(uid,{'usagePreset':'busy'})
    ledger=BudgetLedger(store,enabled=True)
    ledger.reserve(uid,'overrun',100)
    with pytest.raises(ValueError):ledger.settle(uid,'overrun',101,10,1)
    assert ledger.snapshot(uid)['spentMicros']==101
    restarted=BudgetLedger(store,enabled=True)
    with pytest.raises(BudgetDenied):restarted.reserve(uid,'next',100)

def test_unknown_and_known_email_use_one_password_verification(service,monkeypatch):
    store,app=service
    store.create_user('known@example.com','StrongClipBot!2026','K')
    import server.store as module
    original=module.password_hash
    calls=[]
    def measured(*args,**kwargs):
        calls.append(1);return original(*args,**kwargs)
    monkeypatch.setattr(module,'password_hash',measured)
    store.authenticate('known@example.com','wrong-password-long');known=len(calls);calls.clear()
    store.authenticate('missing@example.com','wrong-password-long')
    assert len(calls)==known==1


def test_health_does_not_expose_account_data_and_writes_need_csrf(service):
    store,app=service
    with TestClient(app,client=('127.0.0.1',50000)) as client:
        assert client.get('/healthz').json()=={'status':'ok','mode':'prelaunch'}
        response=signup(client)
        cookie=response.headers['set-cookie']
        assert 'HttpOnly' in cookie and 'SameSite=strict' in cookie
        assert client.put('/api/davey',json={'usagePreset':'busy','focus':'humor','avoid':'personal'},headers={'Origin':'http://testserver'}).status_code==403


def test_candidate_feedback_is_persisted_and_owned_by_account(service):
    store,app=service
    with TestClient(app,client=('127.0.0.1',50000)) as a,TestClient(app,client=('127.0.0.1',50001)) as b:
        signup(a);signup(b,'other@example.com')
        uid=a.get('/api/account').json()['user']['id']
        import json
        with store.connection() as db:
            db.execute('INSERT INTO candidates VALUES(?,?,?)',('actual-worker-id',uid,json.dumps({'id':'actual-worker-id','creator':'Creator','platform':'Twitch','category':'Game','duration':'0:27'})))
        for client in (a,b):assert client.post('/api/beta/accept',json={'version':'beta-feedback-v1'},headers=headers(client)).status_code==200
        payload={'candidate_id':'actual-worker-id','decision':'approve','reasons':['Funny'],'justification':'Clear payoff'}
        assert b.post('/api/reviews',json=payload,headers=headers(b)).status_code==404
        assert a.post('/api/reviews',json=payload,headers=headers(a)).status_code==200
        assert a.post('/api/reviews',json=payload,headers=headers(a)).status_code==200
        workspace=a.get('/api/workspace').json()
        assert workspace['feedbackCount']==1
        assert workspace['reviews'][0]['user_feedback']['decision']=='approve'
        assert b.get('/api/workspace').json()['feedbackCount']==0


def test_chunked_body_cannot_bypass_received_byte_limit(service):
    store,app=service
    with TestClient(app,client=('127.0.0.1',50000)) as client:
        def chunks():
            yield b' ' * 20000
            yield b'{"email":"chunk@example.com","password":"a-good-long-password"}'
        response=client.post('/api/auth/signup',content=chunks(),headers={'Origin':'http://testserver','Content-Type':'application/json'})
        assert response.status_code==413


def test_owner_zero_stop_and_invalid_configuration_fail_closed(service,monkeypatch):
    store,unused=service
    monkeypatch.setenv('CLIPBOT_GLOBAL_MONTHLY_USD','NaN')
    with pytest.raises(RuntimeError):create_app(store,origin='http://testserver')
    monkeypatch.setenv('CLIPBOT_GLOBAL_MONTHLY_USD','0')
    app=create_app(store,origin='http://testserver')
    uid=store.create_user('stop@example.com','StrongClipBot!2026','Stop')
    store.set_coverage(uid,review_daily=120,user_monthly=1000000,scouts=1,favorites=0,categories=0,posts=1)
    store.save_preferences(uid,{'usagePreset':'busy'})
    app.state.ledger.enabled=True
    with pytest.raises(BudgetDenied):app.state.ledger.reserve(uid,'stopped',1)


def test_development_bypass_requires_explicit_local_mode(service,monkeypatch):
    store,unused=service
    monkeypatch.delenv('CLIPBOT_DEV_BYPASS',raising=False)
    closed=create_app(store,origin='http://127.0.0.1:8766',local_signup=True)
    with TestClient(closed,client=('127.0.0.1',50000)) as client:
        assert client.post('/api/auth/dev-bypass',headers={'Origin':'http://127.0.0.1:8766'}).status_code==403
    monkeypatch.setenv('CLIPBOT_DEV_BYPASS','1')
    local=create_app(store,origin='http://127.0.0.1:8766',local_signup=True)
    with TestClient(local,client=('127.0.0.1',50000)) as client:
        assert client.get('/api/auth/options').json()['developmentBypass'] is True
        assert client.post('/api/auth/dev-bypass',headers={'Origin':'http://127.0.0.1:8766'}).status_code==200
        assert client.get('/api/account').json()['user']['name']=='Local Development'
        assert client.get('/api/account').json()['plan']['active'] is False
        assert client.get('/api/usage').json()['aiEnabled'] is False
    with TestClient(local,client=('203.0.113.10',50000)) as remote:
        assert remote.get('/api/auth/options').json()['developmentBypass'] is False
        assert remote.post('/api/auth/dev-bypass',headers={'Origin':'http://127.0.0.1:8766'}).status_code==403
    hosted=create_app(store,origin='https://clipbot.your-domain.example',local_signup=True)
    with TestClient(hosted,client=('127.0.0.1',50000)) as client:
        assert client.post('/api/auth/dev-bypass',headers={'Origin':'https://clipbot.your-domain.example'}).status_code==403


def test_support_reports_validation_privacy_and_limit(service):
    store,app=service
    payload={'kind':'bug','area':'Logs','title':'Errors disappear unexpectedly','details':'The errors disappear when I return to Logs.','steps':'Open Logs, navigate to Davey, then return.','expected':'The errors should remain visible.'}
    with TestClient(app,client=('127.0.0.1',50000)) as a,TestClient(app,client=('127.0.0.1',50000)) as b:
        assert a.post('/api/reports',json=payload,headers={'Origin':'http://testserver'}).status_code==401
        signup(a);signup(b,'two@example.com')
        assert a.post('/api/reports',json=payload,headers={'Origin':'http://testserver'}).status_code==403
        assert a.post('/api/reports',json={**payload,'steps':''},headers=headers(a)).status_code==422
        for i in range(5):
            result=a.post('/api/reports',json={**payload,'title':payload['title']+str(i)},headers=headers(a))
            assert result.status_code==201
            assert result.json()['reference'].startswith('CB-')
        assert a.post('/api/reports',json={**payload,'title':'Different report beyond the limit'},headers=headers(a)).status_code==429
        assert b.get('/api/reports').json()['reports']==[]
        assert len(a.get('/api/reports').json()['reports'])==5


def test_quotes_are_authenticated_and_never_grant_coverage(service):
    store,app=service
    with TestClient(app,client=('127.0.0.1',50000)) as client:
        signup(client)
        assert client.post('/api/billing/quote',json={'plan':'starter'},headers={'Origin':'http://testserver'}).status_code==403
        result=client.post('/api/billing/quote',json={'plan':'starter'},headers=headers(client))
        assert result.json()['monthlyCents']==700
        assert client.post('/api/billing/quote',json={'plan':'starter','monthlyCents':1},headers=headers(client)).status_code==422
        assert client.post('/api/billing/quote',json={'plan':'starter','patreon_verified':True},headers=headers(client)).status_code==422
        assert client.get('/api/account').json()['plan']['active'] is False

def test_live_preview_policy_allows_only_official_players(service):
    _,app=service
    with TestClient(app) as client:
        policy=client.get('/').headers['Content-Security-Policy']
        assert 'frame-src https://player.twitch.tv https://player.kick.com;' in policy
        assert "frame-ancestors 'none'" in policy
        assert "connect-src 'self'" in policy
        assert 'frame-src *' not in policy
