import json
from fastapi.testclient import TestClient
from test_davey_progression import setup,decisions,policy
from test_customer_analysis_release import ready_customer


def test_real_review_transaction_evaluates_first_prediction_and_edit_invalidates(setup):
    store,uid,other,davey=setup;decisions(store,uid,100)
    davey.save(uid,policy(davey,uid,personalContext=True,shadowEnabled=True))
    for index in range(2):
        cid=f'{1000+index:032x}'
        candidate={'id':cid,'score':95,'title':'Moment','caption':'Caption','rationale':'Evidence','start':0,'end':20,'safetyFlags':[]}
        with store.connection() as db:db.execute('INSERT INTO candidates VALUES(?,?,?)',(cid,uid,json.dumps(candidate)))
        assert davey.prediction(uid,cid,candidate,davey.context_key(uid))
        if index:
            with store.connection() as db:db.execute('UPDATE candidates SET data=? WHERE id=?',(json.dumps({**candidate,'title':'Edited'}),cid))
        assert store.save_review(other,cid,'approve',[],'') is False
        store.save_review(uid,cid,'approve',[],'',local_learning=True)
    status=davey.status(uid)
    assert status['validation']['decisions']==1
    store.save_review(uid,f'{1000:032x}','reject',[],'',local_learning=True)
    assert davey.status(uid)['validation']==status['validation']
    with store.connection() as db:
        assert db.execute('SELECT invalidated FROM davey_predictions WHERE job_id=?',(f'{1001:032x}',)).fetchone()[0]==1
        assert json.loads(db.execute('SELECT data FROM reviews WHERE candidate_id=?',(f'{1000:032x}',)).fetchone()[0])['actor']=='human'


def test_actual_analysis_commits_shadow_prediction_before_human_decision(tmp_path,monkeypatch):
    (store,uid,app,messages,*_),body,headers=ready_customer(tmp_path,monkeypatch)
    davey=store.davey;decisions(store,uid,100)
    davey.save(uid,policy(davey,uid,personalContext=True,shadowEnabled=True))
    messages.text=json.dumps({'start':0,'end':20,'score':95,'title':'Moment','caption':'Caption','rationale':'Evidence','safetyFlags':[]})
    with TestClient(app) as client:
        response=client.post('/api/worker/analyze',json=body,headers=headers)
        assert response.status_code==200
        with store.connection() as db:
            row=db.execute('SELECT * FROM davey_predictions WHERE job_id=?',(body['jobId'],)).fetchone()
            assert row is not None and row['human_decision'] is None and row['decision']=='approve'
        session,_=store.new_session(uid);client.cookies.set('clipbot_session',session)
        candidate=next(c for c in client.get('/api/workspace').json()['candidates'] if c['id']==body['jobId'])
        assert candidate['daveyPrediction']=='approve' and candidate['personalContextUsed'] is True
        assert davey.status(uid)['validation']['decisions']==0
        store.save_review(uid,body['jobId'],'approve',[],'',local_learning=True)
        assert davey.status(uid)['validation']['decisions']==1
        # Cached calls cannot rewrite a prediction after seeing the label.
        assert messages.calls==1


def test_legacy_or_flagged_candidates_hold_without_teaching(setup):
    store,uid,_,davey=setup;decisions(store,uid,100)
    davey.save(uid,policy(davey,uid,personalContext=True,shadowEnabled=True))
    for index,flags in enumerate([None,['private_information']]):
        cid=f'{2000+index:032x}'
        candidate={'id':cid,'score':99,'title':'Moment','caption':'Caption','rationale':'Evidence','start':0,'end':20}
        if flags is not None:candidate['safetyFlags']=flags
        with store.connection() as db:db.execute('INSERT INTO candidates VALUES(?,?,?)',(cid,uid,json.dumps(candidate)))
        assert davey.prediction(uid,cid,candidate,davey.context_key(uid))
        store.save_review(uid,cid,'approve',[],'',local_learning=True)
    assert davey.status(uid)['validation']['decisions']==0
