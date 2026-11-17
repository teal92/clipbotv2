import json,time
import pytest
from fastapi.testclient import TestClient
from server.store import Store
from server.budgets import BudgetLedger,BudgetDenied,period
from server.billing_modes import entitlement_allowed
from server.billing_usage import paid_period
from server.scouts import limits_in,ScoutStore
from server.publication import PublicationService
from server.worker_jobs import capture_authorized,WorkerDenied
from server.app import create_app
from test_plan_changes import changes
from test_billing_lifecycle_acceptance import lifecycle
from test_publication import setup as publication_setup


@pytest.fixture
def showcase(tmp_path,monkeypatch):
    store=Store(tmp_path/'showcase.db');store.billing_mode='live'
    uid=store.create_user('owner@example.com','StrongClipBot!2026','owner')
    monkeypatch.setenv('CLIPBOT_ADMIN_USER_ID',uid)
    with store.connection() as db:
        db.execute('INSERT INTO guards VALUES(?,?)',('owner_showcase:'+uid,json.dumps({'enabled':True})))
    store.save_preferences(uid,{'usagePreset':'busy'})
    return store,uid


def test_owner_has_max_custom_without_payment_records(showcase):
    store,uid=showcase
    result=store.coverage(uid)
    assert result is not None
    assert {k:result[k] for k in ('review_daily','user_monthly','scouts','favorites','categories')}==dict(review_daily=180,user_monthly=12000000,scouts=40,favorites=25,categories=25)
    assert result['ownerShowcase'] is True and result['uniqueClipsDaily'] is None
    with store.connection() as db:
        assert entitlement_allowed(db,uid)
        assert paid_period(db,uid) is None
        assert db.execute('SELECT COUNT(*) FROM billing_state').fetchone()[0]==0
        assert limits_in(db,uid)==dict(scouts=40,favorites=25,categories=25)
        _,billing=PublicationService.active_coverage(db,uid)
        assert billing['plan']=='custom'


@pytest.mark.parametrize('invalid',['other_owner','no_owner','disabled','string_true','bad_json','dev_account'])
def test_showcase_never_grants_customer_or_invalid_owner(showcase,monkeypatch,invalid):
    store,uid=showcase
    with store.connection() as db:
        if invalid=='other_owner':monkeypatch.setenv('CLIPBOT_ADMIN_USER_ID','f'*32)
        elif invalid=='no_owner':monkeypatch.delenv('CLIPBOT_ADMIN_USER_ID')
        elif invalid=='disabled':db.execute('UPDATE guards SET value=?',(json.dumps({'enabled':False}),))
        elif invalid=='string_true':db.execute('UPDATE guards SET value=?',(json.dumps({'enabled':'true'}),))
        elif invalid=='bad_json':db.execute("UPDATE guards SET value='broken'")
        elif invalid=='dev_account':db.execute("UPDATE users SET email='clipbot-local-development@example.invalid' WHERE id=?",(uid,))
    assert store.coverage(uid) is None
    other=store.create_user('customer@example.com','StrongClipBot!2026','customer')
    with store.connection() as db:
        db.execute('INSERT INTO guards VALUES(?,?)',('owner_showcase:'+other,json.dumps({'enabled':True})))
        assert not entitlement_allowed(db,other)
        assert limits_in(db,other)==dict(scouts=0,favorites=0,categories=0)


def test_showcase_does_not_modify_real_stripe_records(showcase):
    store,uid=showcase
    with store.connection() as db:
        db.execute('INSERT INTO billing_state VALUES(?,?,?,?,?,?,?,?)',(uid,'sub_real','cus_real','pro','inactive',0,3600,None))
        before=tuple(db.execute('SELECT * FROM billing_state WHERE user_id=?',(uid,)).fetchone())
    ledger=BudgetLedger(store,enabled=True)
    ledger.reserve(uid,'showcase',1000)
    ledger.settle(uid,'showcase',900,500,100)
    assert ledger.snapshot(uid)['monthlyReviewLimit']==5400
    with store.connection() as db:
        assert tuple(db.execute('SELECT * FROM billing_state WHERE user_id=?',(uid,)).fetchone())==before
    assert store.coverage(uid)['review_daily']==180


def test_revocation_is_immediate_without_erasing_usage(showcase):
    store,uid=showcase;ledger=BudgetLedger(store,enabled=True)
    ledger.reserve(uid,'in-flight',1000)
    with store.connection() as db:db.execute('DELETE FROM guards WHERE key=?',('owner_showcase:'+uid,))
    assert store.coverage(uid) is None
    with pytest.raises(BudgetDenied):ledger.reserve(uid,'new-review',1)
    ledger.settle(uid,'in-flight',900,500,100)
    assert ledger.snapshot(uid)['spentMicros']==900


def test_showcase_does_not_satisfy_real_email_or_policy_verification(showcase,monkeypatch):
    from server.analysis_api import customer_enabled
    from server.customer_access import CustomerAccess
    from server.legal import POLICY_VERSION
    store,uid=showcase;monkeypatch.setenv('CLIPBOT_CUSTOMER_ANALYSIS_ENABLED','1')
    access=CustomerAccess(store,'https://example.test',config={'enabled':False})
    assert access.readiness(uid)['ready'] is False
    assert customer_enabled(store,uid) is False
    with store.connection() as db:
        db.execute('INSERT INTO email_verification VALUES(?,?)',(uid,time.time()))
        db.execute('INSERT INTO legal_acceptances VALUES(?,?,?)',(uid,POLICY_VERSION,time.time()))
    assert customer_enabled(store,uid) is True


@pytest.mark.parametrize('boundary',['daily_spend','monthly_spend','daily_reviews','monthly_reviews','global','paused'])
def test_showcase_respects_limits(showcase,boundary):
    store,uid=showcase;day,month=period()
    ledger=BudgetLedger(store,enabled=True)
    with store.connection() as db:
        if boundary=='daily_spend':
            db.execute("INSERT INTO jobs VALUES(?,?,?,?,0,400000,0,0,'settled')",(uid,'used',day,month))
        elif boundary=='monthly_spend':
            db.execute("INSERT INTO jobs VALUES(?,?,?,?,0,12000000,0,0,'settled')",(uid,'used','2000-01-01',month))
        elif boundary in ('daily_reviews','monthly_reviews'):
            count=180 if boundary=='daily_reviews' else 5400
            used_day=day if boundary=='daily_reviews' else '2000-01-01'
            db.executemany("INSERT INTO jobs VALUES(?,?,?,?,0,0,0,0,'settled')",[(uid,str(i),used_day,month) for i in range(count)])
        elif boundary=='global':ledger.global_daily=0
        elif boundary=='paused':db.execute('UPDATE preferences SET data=? WHERE user_id=?',(json.dumps({'usagePreset':'paused'}),uid))
    expected={'daily_spend':'daily spending','monthly_spend':'AI spending','daily_reviews':'daily review',
              'monthly_reviews':'Monthly review','global':'Service spending','paused':'daily spending'}
    with pytest.raises(BudgetDenied,match=expected[boundary]):ledger.reserve(uid,'over',1)


def test_capture_still_requires_running_scouts(showcase):
    store,uid=showcase;scouts=ScoutStore(store)
    with store.connection() as db:
        with pytest.raises(WorkerDenied):capture_authorized(db,uid)
    scouts.save(uid,dict(running=True,slots=1,forced=[],favorites=[],categories=[]))
    with store.connection() as db:capture_authorized(db,uid)


def test_showcase_is_excluded_from_real_paid_proration(changes,monkeypatch):
    store,uid,other,provider,billing,clock=changes
    monkeypatch.setenv('CLIPBOT_ADMIN_USER_ID',uid)
    with store.connection() as db:db.execute('INSERT INTO guards VALUES(?,?)',('owner_showcase:'+uid,json.dumps({'enabled':True})))
    assert store.coverage(uid)['user_monthly']==12000000
    assert billing.change(uid,'creator')['status']=='applied'
    with store.connection() as db:db.execute('DELETE FROM guards WHERE key=?',('owner_showcase:'+uid,))
    assert 4600000<=store.coverage(uid)['user_monthly']<=4700000


def test_showcase_reports_and_resumes_despite_canceled_paid_subscription(showcase):
    from server.worker_jobs import WorkerJobs
    from server.billing_modes import cancellation_revoked
    store,uid=showcase;scouts=ScoutStore(store);jobs=WorkerJobs(store)
    scouts.save(uid,dict(running=True,slots=1,forced=[],favorites=[],categories=[]))
    with store.connection() as db:
        db.execute('INSERT INTO billing_state VALUES(?,?,?,?,?,?,?,?)',(uid,'sub_old','cus_old','pro','inactive',0,3600,None))
        db.execute("INSERT INTO billing_access_revocations VALUES(?,?,?,?)",(uid,'sub_old','live',time.time()))
        assert cancellation_revoked(db,uid)
    token=store.connect_worker(store.new_pairing(uid));job=jobs.open(token,{'platform':'twitch','login':'owner'})
    jobs.report(token,job['id'],job['lease'],{'stage':'capturing'})
    jobs.report(token,job['id'],job['lease'],{'stage':'transcribing'})
    with store.connection() as db:db.execute('UPDATE pipeline_jobs SET lease_expires=0 WHERE id=?',(job['id'],))
    assert jobs.resume(token,job['id'])['stage']=='transcribing'
    with store.connection() as db:db.execute('DELETE FROM guards WHERE key=?',('owner_showcase:'+uid,))
    with pytest.raises(WorkerDenied):jobs.open(token,{'platform':'kick','login':'other'})


def test_showcase_finishes_publication_without_changing_paid_cancellation(publication_setup,monkeypatch):
    from server.billing_modes import cancellation_revoked
    from server.publication import PublicationDenied
    store,uid,oauth,jobs,pub=publication_setup
    monkeypatch.setenv('CLIPBOT_ADMIN_USER_ID',uid)
    with store.connection() as db:
        db.execute('INSERT INTO guards VALUES(?,?)',('owner_showcase:'+uid,json.dumps({'enabled':True})))
        db.execute('INSERT INTO billing_state VALUES(?,?,?,?,?,?,?,?)',(uid,'sub_old','cus_old','pro','inactive',0,3600,None))
        db.execute('INSERT INTO billing_access_revocations VALUES(?,?,?,?)',(uid,'sub_old','test',time.time()))
    job=jobs.enqueue(uid,{'platform':'twitch','login':'owner'})
    pub.artifact(uid,job,{'sha256':'a'*64,'sizeBytes':1000,'duration':20})
    with store.connection() as db:db.execute("UPDATE pipeline_jobs SET stage='ready' WHERE id=?",(job,))
    oauth.vault.save(uid,'facebook',{'access_token':'OWNER','expires_at':time.time()+3600,'destinations':[{'id':'111','page_id':'111','name':'Page','access_token':'PAGE'}]}, {'id':'owner','name':'Owner','destinationSelected':True,'destinationId':'111'})
    finishes=[]
    def request(method,url,**kwargs):
        phase=kwargs.get('data',{}).get('upload_phase')
        if phase=='start':return {'video_id':'123','upload_url':'https://rupload.facebook.com/video-upload/v24.0/123'}
        if phase=='finish':finishes.append(1);return {'success':True}
        return {'status':{'publishing_phase':{'status':'not_started'},'uploading_phase':{'status':'complete'}}}
    oauth.request=request
    attempt=pub.prepare(uid,job,'facebook',{'title':'Title','caption':'Caption','rightsAccepted':True})
    token=store.connect_worker(store.new_pairing(uid));pub.grant(token,attempt['id'])
    assert pub.uploaded(token,attempt['id'])['status']=='finishing'
    assert finishes==[1]
    with store.connection() as db:
        assert cancellation_revoked(db,uid)
        db.execute('DELETE FROM guards WHERE key=?',('owner_showcase:'+uid,))
    with pytest.raises(PublicationDenied):pub.reserve(uid,'new-clip','facebook')


def test_account_discloses_showcase_and_preserves_billing(showcase):
    store,uid=showcase
    app=create_app(store,origin='http://testserver',local_signup=False)
    token,_=store.new_session(uid)
    with TestClient(app) as client:
        client.cookies.set('clipbot_session',token)
        result=client.get('/api/account').json()
    assert result['plan']['name']=='Custom · Owner showcase'
    assert result['plan']['coverage']['ownerShowcase'] is True
    assert result['billing']['subscription'] is None
