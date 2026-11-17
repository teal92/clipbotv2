"""Attack strings must stay data, including after storage and later reads."""
import json
import pytest
from fastapi.testclient import TestClient
from server.app import create_app
from server.store import Store
from server.report_delivery import ReportDelivery
from test_report_delivery import report

PAYLOADS=["' OR 1=1 --", "'; DROP TABLE users; --", "' UNION SELECT id,email,password,name,created FROM users --", "\"; DELETE FROM coverage; --", "Robert'); DROP TABLE reviews;--"]

@pytest.mark.parametrize('payload',PAYLOADS)
def test_local_personal_memory_never_executes_feedback_or_confirmation_inputs(tmp_path,payload):
    from worker.personal_memory import PersonalMemory
    memory=PersonalMemory(tmp_path,'https://clipbot.example.test','a'*32)
    other=PersonalMemory(tmp_path,'https://clipbot.example.test','b'*32)
    memory.record('c'*32,'approve',['Strong hook'],payload)
    memory.confirm([{'candidateId':payload,'decision':"' OR 1=1 --"}])
    assert memory.review('c'*32)=={'decision':'approve','reasons':['Strong hook'],'justification':payload,'confirmed':False}
    memory.confirm([{'candidateId':'c'*32,'decision':'approve'}])
    assert memory.summary()['reviewCount']==1
    assert other.review('c'*32) is None

@pytest.mark.parametrize('payload',PAYLOADS)
def test_login_inputs_cannot_bypass_authentication_or_change_database(tmp_path,payload):
    store=Store(tmp_path/'login.db')
    uid=store.create_user('victim@example.test','StrongPassword!2026','victim')
    app=create_app(store,origin='http://testserver')
    with TestClient(app) as client:
        for email,password in [(payload,'WrongPassword!2026'),('victim@example.test',payload)]:
            response=client.post('/api/auth/login',json={'email':email,'password':password},headers={'Origin':'http://testserver'})
            assert response.status_code in (401,422)
            assert 'clipbot_session' not in response.cookies
    assert store.authenticate('victim@example.test','StrongPassword!2026')==uid
    with store.connection() as db:
        assert db.execute('SELECT COUNT(*) FROM users').fetchone()[0]==1
        assert db.execute('SELECT COUNT(*) FROM sessions').fetchone()[0]==0

@pytest.mark.parametrize('payload',PAYLOADS)
def test_stored_reports_and_davey_feedback_remain_literal_and_account_owned(tmp_path,payload):
    store=Store(tmp_path/'stored.db')
    uid=store.create_user('owner@example.test','StrongPassword!2026','owner')
    other=store.create_user('other@example.test','StrongPassword!2026','other')
    candidate_id=payload
    candidate={'id':candidate_id,'title':payload,'caption':payload,'rationale':payload,'start':0,'end':20,'score':80}
    with store.connection() as db:
        db.execute('INSERT INTO candidates VALUES(?,?,?)',(candidate_id,uid,json.dumps(candidate)))
    delivery=ReportDelivery(store,config={})
    reference=delivery.submit(uid,payload,report(payload))['reference']
    assert store.save_review(other,candidate_id,'reject',[],payload) is False
    assert store.save_review(uid,candidate_id,'reject',[],payload) is True
    assert store.workspace_feedback(other)==([],[],0)
    _,reviews,count=store.workspace_feedback(uid)
    assert count==1 and reviews[0]['user_feedback']['justification']==payload
    assert reviews[0]['candidate']['title']==payload
    assert delivery.receipts(uid)[0]['reference']==reference
    assert delivery.receipts(other)==[]
    with pytest.raises(ValueError):store.update_profile(uid,payload)
    assert store.user(other)['username']=='other'
    with store.connection() as db:
        assert db.execute('SELECT COUNT(*) FROM users').fetchone()[0]==2
        assert db.execute('SELECT COUNT(*) FROM reports').fetchone()[0]==1
        assert db.execute('SELECT COUNT(*) FROM candidates').fetchone()[0]==1
