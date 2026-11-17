import time
from concurrent.futures import ThreadPoolExecutor

import pytest
from cryptography.fernet import Fernet
from server.store import Store
from server.scouts import ScoutStore
from server.worker_jobs import WorkerJobs, WorkerDenied
from server.publication import PublicationService, PublicationDenied
from server.oauth import OAuthService


@pytest.fixture
def paid(tmp_path, monkeypatch):
    monkeypatch.setenv('CLIPBOT_TOKEN_ENCRYPTION_KEY', Fernet.generate_key().decode())
    store = Store(tmp_path / 'paid.db')
    uid = store.create_user('paid@example.com', 'a-good-long-password', 'Paid')
    store.set_coverage(uid, review_daily=15, user_monthly=1000000, scouts=6, favorites=2, categories=2, posts=20)
    with store.connection() as db:
        db.execute('INSERT INTO billing_state(user_id,subscription,customer,plan,status,expires) VALUES(?,?,?,?,?,?)', (uid, 'sub', 'customer', 'starter', 'active', time.time()+3600))
    token = store.connect_worker(store.new_pairing(uid))
    scouts = ScoutStore(store)
    scouts.save(uid, {'running':True,'slots':2,'platformSlots':{'twitch':1,'kick':1},'forced':[],'favorites':[],'categories':[]})
    jobs = WorkerJobs(store)
    oauth = OAuthService(store, 'https://clipbot.example')
    return store, uid, token, scouts, jobs, oauth, PublicationService(store, oauth)


@pytest.mark.parametrize('operation', ['claim', 'report'])
@pytest.mark.parametrize('expired', [True, False])
def test_paid_worker_cannot_continue_after_entitlement_loss(paid, operation, expired):
    store, uid, token, scouts, jobs, oauth, pub = paid
    job = jobs.open(token, {'platform':'twitch','login':'one'})
    with store.connection() as db:
        if operation == 'claim':
            db.execute('UPDATE pipeline_jobs SET lease_expires=0 WHERE id=?', (job['id'],))
        db.execute('UPDATE billing_state SET status=?,expires=? WHERE user_id=?', ('active' if expired else 'inactive', time.time()-1 if expired else time.time()+3600, uid))
    with pytest.raises(WorkerDenied):
        if operation == 'claim': jobs.claim(token)
        else: jobs.report(token, job['id'], job['lease'], {'stage':'capturing'})


def test_daily_destination_limit_counts_prior_day_crossposts_and_unknown_attempts(paid):
    store, uid, token, scouts, jobs, oauth, pub = paid
    # Yesterday's clips do not spend today's unique allowance; crossposting them
    # still consumes today's destination allowance even if outcome is unknown.
    for i in range(19):
        pub.reserve(uid, 'old'+str(i), 'instagram')
    with store.connection() as db:
        db.execute("UPDATE clip_capacity SET day='2000-01-01'")
        db.execute("UPDATE publications SET day='2000-01-01'")
    for i in range(19):
        attempt = pub.reserve(uid, 'old'+str(i), 'facebook')
        with store.connection() as db: db.execute("UPDATE publications SET status='unknown' WHERE id=?", (attempt,))
    def reserve(i):
        try: return pub.reserve(uid, 'new'+str(i), 'facebook')
        except PublicationDenied: return None
    with ThreadPoolExecutor(max_workers=5) as pool:
        attempts = list(pool.map(reserve, range(5)))
    assert sum(attempt is not None for attempt in attempts) == 1
    assert pub.reserve(uid, 'old0', 'tiktok')


def prepared(paid):
    store, uid, token, scouts, jobs, oauth, pub = paid
    job = jobs.enqueue(uid, {'platform':'twitch','login':'one'})
    pub.artifact(uid, job, {'sha256':'a'*64,'sizeBytes':1000,'duration':20})
    with store.connection() as db: db.execute("UPDATE pipeline_jobs SET stage='ready' WHERE id=?", (job,))
    if not oauth.vault.load(uid, 'facebook'): oauth.vault.save(uid, 'facebook', {'access_token':'OWNER','expires_at':time.time()+3600,'destinations':[{'id':'111','name':'Page','access_token':'PAGE'}]}, {'id':'owner','destinationSelected':True,'destinationId':'111'})
    def request(method, url, **kwargs):
        if kwargs.get('data', {}).get('upload_phase') == 'start': return {'video_id':'123','upload_url':'https://rupload.facebook.com/video-upload/v24.0/123'}
        return {'status':{'uploading_phase':{'status':'complete'}}}
    oauth.request = request
    return pub.prepare(uid, job, 'facebook', {'title':'Title','caption':'Caption','rightsAccepted':True})


def test_upload_grant_denied_when_paid_plan_expires(paid):
    store, uid, token, scouts, jobs, oauth, pub = paid
    attempt = prepared(paid)
    with store.connection() as db: db.execute('UPDATE billing_state SET expires=0 WHERE user_id=?', (uid,))
    with pytest.raises(PublicationDenied): pub.grant(token, attempt['id'])
    assert pub.snapshot(uid)[0]['status'] == 'prepared'


def test_granted_upload_can_finish_after_expiry_but_not_reauthorization(paid):
    store, uid, token, scouts, jobs, oauth, pub = paid
    attempt = prepared(paid)
    pub.grant(token, attempt['id'])
    with store.connection() as db:
        db.execute("UPDATE publications SET status='uploaded',lease_owner='poll',lease_expires=? WHERE id=?", (time.time()+30, attempt['id']))
        row = db.execute('SELECT * FROM publications WHERE id=?', (attempt['id'],)).fetchone()
        db.execute('UPDATE billing_state SET expires=0 WHERE user_id=?', (uid,))
    # Paid expiry must not strand an upload already granted to the provider.
    assert pub.finishing(uid, row, 'poll')
    with store.connection() as db:
        db.execute("UPDATE publications SET status='uploaded',finish_started=0 WHERE id=?", (attempt['id'],))
    oauth.vault.save(uid, 'facebook', {'access_token':'NEW','expires_at':time.time()+3600,'destinations':[{'id':'111','name':'Page','access_token':'NEWPAGE'}]}, {'id':'owner','destinationSelected':True,'destinationId':'111'})
    with pytest.raises(PublicationDenied): pub.finishing(uid, row, 'poll')
    assert pub.snapshot(uid)[0]['status'] == 'uploaded'


@pytest.mark.parametrize('change', ['stop', 'zero_scouts', 'no_coverage'])
def test_paid_claim_and_new_capture_stop_when_coverage_is_removed(paid, change):
    store, uid, token, scouts, jobs, oauth, pub = paid
    job = jobs.open(token, {'platform':'twitch','login':'one'})
    with store.connection() as db:
        db.execute('UPDATE pipeline_jobs SET lease_expires=0 WHERE id=?', (job['id'],))
        if change == 'stop':
            db.execute("UPDATE scout_settings SET data=json_set(data,'$.running',json('false')) WHERE user_id=?", (uid,))
        elif change == 'zero_scouts': db.execute('UPDATE coverage SET scouts=0 WHERE user_id=?', (uid,))
        else: db.execute('DELETE FROM coverage WHERE user_id=?', (uid,))
    with pytest.raises(WorkerDenied): jobs.claim(token)
    with pytest.raises(WorkerDenied): jobs.open(token, {'platform':'kick','login':'two'})


def test_captured_work_and_failure_accounting_survive_stop_or_expiry(paid):
    store, uid, token, scouts, jobs, oauth, pub = paid
    job = jobs.open(token, {'platform':'twitch','login':'one'})
    jobs.report(token, job['id'], job['lease'], {'stage':'capturing'})
    with store.connection() as db:
        db.execute('UPDATE billing_state SET expires=0 WHERE user_id=?', (uid,))
    assert jobs.report(token, job['id'], job['lease'], {'stage':'transcribing'})['ok']
    assert jobs.report(token, job['id'], job['lease'], {'stage':'failed','errorCode':'cancelled'})['ok']

def test_explicit_cancellation_blocks_existing_worker_work_and_publish_finalization(paid):
    from server.immediate_cancellation import revoke
    store,uid,token,scouts,jobs,oauth,pub=paid
    job=jobs.open(token,{'platform':'twitch','login':'one'})
    jobs.report(token,job['id'],job['lease'],{'stage':'capturing'})
    attempt=prepared(paid);pub.grant(token,attempt['id'])
    with store.connection() as db:
        db.execute("UPDATE publications SET status='uploaded',lease_owner='poll',lease_expires=? WHERE id=?",(time.time()+30,attempt['id']))
        row=db.execute('SELECT * FROM publications WHERE id=?',(attempt['id'],)).fetchone()
        revoke(db,uid,'sub','test',time.time())
    with pytest.raises(PublicationDenied):pub.finishing(uid,row,'poll')
    with pytest.raises(WorkerDenied):jobs.report(token,job['id'],job['lease'],{'stage':'transcribing'})
    with pytest.raises(WorkerDenied):jobs.resume(token,job['id'])
    # A stopped job can still report failure and release already reserved costs.
    assert jobs.report(token,job['id'],job['lease'],{'stage':'failed','errorCode':'cancelled'})['ok']
    assert scouts.snapshot(uid)['configuration']['running'] is False
    assert scouts.snapshot(uid)['effective']['running'] is False



def test_midnight_carryover_grants_share_current_daily_unique_and_post_capacity(paid):
    store, uid, token, scouts, jobs, oauth, pub = paid
    # Real prepare creates encrypted, valid provider grants, then shift only
    # their accounting day to model initialization immediately before midnight.
    attempts = [prepared(paid) for _ in range(5)]
    with store.connection() as db:
        db.execute("UPDATE publications SET day='2000-01-01'")
        db.execute("UPDATE clip_capacity SET day='2000-01-01'")
    for i in range(19): pub.reserve(uid, 'today'+str(i), 'facebook')
    def grant(attempt):
        try: return pub.grant(token, attempt['id'])
        except PublicationDenied: return None
    with ThreadPoolExecutor(max_workers=5) as pool:
        grants = list(pool.map(grant, attempts))
    accepted = [grant for grant in grants if grant]
    assert len(accepted) == 1
    with store.connection() as db:
        assert db.execute("SELECT COUNT(*) FROM clip_capacity WHERE user_id=? AND day!='2000-01-01'", (uid,)).fetchone()[0] == 20
        row = db.execute('SELECT day FROM publications WHERE id=?', (accepted[0]['attemptId'],)).fetchone()
        assert row['day'] != '2000-01-01'
    with pytest.raises(PublicationDenied): pub.grant(token, accepted[0]['attemptId'])
    with store.connection() as db:
        assert db.execute("SELECT COUNT(*) FROM clip_capacity WHERE user_id=? AND day!='2000-01-01'", (uid,)).fetchone()[0] == 20



def test_same_day_downgrade_cannot_grant_above_new_paid_clip_allowance(paid):
    store, uid, token, scouts, jobs, oauth, pub = paid
    with store.connection() as db: db.execute("UPDATE billing_state SET plan='pro' WHERE user_id=?", (uid,))
    attempt = prepared(paid)
    for i in range(24): pub.reserve(uid, 'pro'+str(i), 'facebook')
    with store.connection() as db: db.execute("UPDATE billing_state SET plan='starter' WHERE user_id=?", (uid,))
    with pytest.raises(PublicationDenied): pub.grant(token, attempt['id'])
    assert next(row for row in pub.snapshot(uid) if row['id'] == attempt['id'])['status'] == 'prepared'
