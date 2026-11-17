import json
from fastapi.testclient import TestClient
from server.app import create_app
from server.store import Store

def setup(tmp_path,monkeypatch):
    store=Store(tmp_path/'admin.db')
    owner=store.create_user('owner@example.com','a-good-long-password','Owner')
    other=store.create_user('other@example.com','a-good-long-password','Other')
    monkeypatch.setenv('CLIPBOT_ADMIN_USER_ID',owner)
    monkeypatch.setenv('CLIPBOT_C2_SERVICE_KEY','test-private-service-key-01234567890123456789')
    app=create_app(store,origin='http://testserver',local_signup=False)
    return store,app,owner,other

def service_headers():return {'Authorization':'Bearer test-private-service-key-01234567890123456789'}

def login(client,email):
    response=client.post('/api/auth/login',json={'email':email,'password':'a-good-long-password'},headers={'Origin':'http://testserver'})
    assert response.status_code==200
    return {'Origin':'http://testserver','X-CSRF-Token':response.json()['csrfToken']}

def test_metrics_require_private_service_key_even_for_browser_owner(tmp_path,monkeypatch):
    store,app,owner,other=setup(tmp_path,monkeypatch)
    with TestClient(app) as c:
        assert c.get('/api/admin/metrics').status_code==404
        assert c.get('/api/operator/metrics').status_code==401
        login(c,'other@example.com')
        assert c.get('/api/admin/metrics').status_code==404
        assert c.get('/api/operator/metrics').status_code==401
        assert c.get('/api/account').json()['isAdmin'] is False
        login(c,'owner@example.com')
        assert c.get('/api/account').json()['isAdmin'] is True
        assert c.get('/api/operator/metrics').status_code==401
        assert c.get('/api/operator/metrics',headers={'Authorization':'Bearer incorrect-private-service-key'}).status_code==401
        data=c.get('/api/operator/metrics',headers=service_headers()).json()
        assert data['registeredUsers']==1
        assert data['inputTokens']==data['outputTokens']==0
        assert data['publishingAvailable'] is True
        assert set(data['platformPosts'])=={'tiktok','instagram','facebook'}
        assert data['activeUsers']==0
        assert c.post('/api/presence',headers=login(c,'owner@example.com')).status_code==200
        assert c.get('/api/operator/metrics',headers=service_headers()).json()['activeUsers']==0
        serialized=json.dumps(data)
        assert 'owner@example.com' not in serialized
        assert owner not in serialized and 'password' not in serialized
        # Private service totals are intentional; customer rankings still exclude the owner.
        assert data['capacityUsage']['daily']['spentMicros']==0
        assert all(not rows for rows in data['capacityUsage']['topUsers'].values())

def test_operator_metrics_disabled_without_service_key(tmp_path,monkeypatch):
    store,app,owner,other=setup(tmp_path,monkeypatch)
    monkeypatch.delenv('CLIPBOT_C2_SERVICE_KEY')
    monkeypatch.setenv('CLIPBOT_C2_SERVICE_KEY_FILE',str(tmp_path/'missing.key'))
    with TestClient(create_app(store,origin='http://testserver')) as c:
        login(c,'owner@example.com')
        assert c.get('/api/admin/metrics').status_code==404
        assert c.get('/api/operator/metrics',headers=service_headers()).status_code==404

def test_beta_feedback_requires_acknowledgment_and_excludes_private_text(tmp_path,monkeypatch):
    store,app,owner,other=setup(tmp_path,monkeypatch)
    with store.connection() as db:db.execute('INSERT INTO candidates VALUES(?,?,?)',('clip-one',owner,json.dumps({'id':'clip-one','transcript':'PRIVATE TRANSCRIPT','title':'PRIVATE TITLE'})))
    with TestClient(app) as c:
        headers=login(c,'owner@example.com')
        body={'candidate_id':'clip-one','decision':'approve','reasons':['Funny'],'justification':'PRIVATE REASON'}
        assert c.post('/api/reviews',json=body,headers=headers).status_code==428
        assert c.post('/api/beta/accept',json={'version':'wrong'},headers=headers).status_code==422
        assert c.post('/api/beta/accept',json={'version':'beta-feedback-v1'},headers={'Origin':'http://testserver'}).status_code==403
        assert c.post('/api/beta/accept',json={'version':'beta-feedback-v1'},headers=headers).status_code==200
        assert c.post('/api/reviews',json=body,headers=headers).status_code==200
        assert c.post('/api/reviews',json=body,headers=headers).status_code==200
        data=c.get('/api/operator/metrics',headers=service_headers()).json()
        assert data['learning']['betaParticipants']==0
        assert data['learning']['reasonCoverage']==0
        assert data['learning']['precision'] is None
        assert data['learning']['validationAvailable'] is False
        assert data['sharedDecisions']==0
        assert data['feedbackReasons']=={}
        with store.connection() as db:
            shared=[dict(r) for r in db.execute('SELECT * FROM shared_feedback')]
        assert 'PRIVATE' not in json.dumps(shared)
        assert 'transcript' not in json.dumps(shared)


def test_metrics_report_recorded_tokens_and_expire_presence(tmp_path,monkeypatch):
    store,app,owner,other=setup(tmp_path,monkeypatch)
    with store.connection() as db:
        db.execute("INSERT INTO jobs(user_id,job_id,day,month,reserved,spent,input_tokens,output_tokens,state) VALUES(?,?,?,?,?,?,?,?,?)",(other,'real-test-result','2026-10-11','2026-10',0,3000,20000,2000,'settled'))
    with TestClient(app) as c:
        headers=login(c,'other@example.com')
        c.post('/api/presence',headers=headers)
        data=c.get('/api/operator/metrics',headers=service_headers()).json()
        assert data['inputTokens']==20000 and data['outputTokens']==2000
        assert data['completedReviews']==1 and data['activeUsers']==1
        with store.connection() as db:db.execute('UPDATE session_presence SET last_seen=0')
        assert c.get('/api/operator/metrics',headers=service_headers()).json()['activeUsers']==0
        assert c.post('/api/auth/logout',headers=headers).status_code==200
        assert c.get('/api/admin/metrics').status_code==404
        assert c.get('/api/operator/metrics').status_code==401
