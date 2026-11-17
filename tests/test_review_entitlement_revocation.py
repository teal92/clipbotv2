import json,time
import pytest
from fastapi.testclient import TestClient
from server.app import create_app
from test_billing_release_management import payer


@pytest.mark.parametrize('uncertain',[False,True])
def test_cancel_blocks_review_and_learning_before_provider_reconciliation(payer,uncertain):
    store,uid,provider,billing=payer
    cid='e'*32
    store.accept_beta(uid)
    with store.connection() as db:
        db.execute('INSERT INTO candidates VALUES(?,?,?)',(cid,uid,json.dumps({'id':cid,'title':'Existing candidate','score':80})))
    app=create_app(store,origin='http://testserver',billing=billing)
    token,csrf=store.new_session(uid)
    before=app.state.davey.status(uid)
    def cancel_now(id,key):
        # The review mutation must already be denied while the provider call is pending.
        with pytest.raises(ValueError,match='active subscription'):
            store.save_review(uid,cid,'reject',[],'',local_learning=True)
        if uncertain:raise TimeoutError('synthetic uncertain cancellation')
        return {**provider.subscription(id),'status':'canceled','ended_at':int(time.time())}
    provider.cancel_now=cancel_now
    if uncertain:
        with pytest.raises(TimeoutError):billing.cancel(uid)
    else:billing.cancel(uid)
    with TestClient(app) as client:
        client.cookies.set('clipbot_session',token)
        result=client.post('/api/reviews',headers={'Origin':'http://testserver','X-CSRF-Token':csrf},json={'candidate_id':cid,'decision':'reject','localLearning':True})
        assert result.status_code==409
        assert 'active subscription' in result.json()['detail']
    with store.connection() as db:assert db.execute('SELECT COUNT(*) FROM reviews WHERE user_id=?',(uid,)).fetchone()[0]==0
    assert app.state.davey.status(uid)==before


def test_expired_subscription_cannot_mutate_review(payer):
    store,uid,provider,billing=payer
    cid='d'*32
    with store.connection() as db:
        db.execute('INSERT INTO candidates VALUES(?,?,?)',(cid,uid,json.dumps({'id':cid})))
        db.execute('UPDATE billing_state SET expires=? WHERE user_id=?',(time.time()-1,uid))
    with pytest.raises(ValueError,match='active subscription'):
        store.save_review(uid,cid,'approve',[],'')


@pytest.mark.parametrize('begin_first',[False,True])
def test_revoked_subscription_cannot_begin_or_complete_local_edit(tmp_path,begin_first):
    from test_clip_edits import setup_edit
    store,uid,client,headers,body,artifact=setup_edit(tmp_path)
    if begin_first:
        started=client.post('/api/worker/clip-edits/begin',json=body,headers=headers)
        assert started.status_code==200
    with store.connection(atomic=True) as db:
        db.execute('INSERT INTO billing_state VALUES(?,?,?,?,?,?,?,?)',(uid,'sub_revoked','cus_edit','starter','active',time.time()+86400,450,'r'))
        db.execute("INSERT INTO billing_access_revocations VALUES(?,?,'test',?)",(uid,'sub_revoked',time.time()))
    if begin_first:
        payload={'jobId':body['jobId'],'editId':started.json()['editId'],'artifact':{**artifact,'duration':20},'previewToken':'c'*64}
        result=client.post('/api/worker/clip-edits/complete',json=payload,headers=headers)
    else:result=client.post('/api/worker/clip-edits/begin',json=body,headers=headers)
    assert result.status_code==409
    assert 'active subscription' in result.json()['detail']
    with store.connection() as db:
        saved=json.loads(db.execute('SELECT data FROM candidates WHERE id=?',(body['jobId'],)).fetchone()[0])
        assert saved['title']=='Original'


@pytest.mark.parametrize('route',['render-ready','candidate-preview-ready'])
def test_revocation_blocks_new_artifact_registration_with_an_existing_lease(tmp_path,route):
    from test_clip_edits import setup_edit
    store,uid,client,headers,body,artifact=setup_edit(tmp_path)
    with store.connection(atomic=True) as db:
        db.execute('INSERT INTO billing_state VALUES(?,?,?,?,?,?,?,?)',(uid,'sub_revoked','cus_edit','starter','active',time.time()+86400,450,'r'))
        db.execute("INSERT INTO billing_access_revocations VALUES(?,?,'test',?)",(uid,'sub_revoked',time.time()))
        original=db.execute('SELECT data FROM clip_artifacts WHERE clip_id=?',(body['jobId'],)).fetchone()[0]
    payload={k:body[k] for k in ('jobId','lease')};payload['previewToken']='f'*64
    if route=='render-ready':payload['artifact']={**artifact,'sha256':'f'*64}
    result=client.post('/api/worker/'+route,json=payload,headers=headers)
    assert result.status_code==409
    assert 'active subscription' in result.json()['detail']
    with store.connection() as db:
        assert db.execute('SELECT data FROM clip_artifacts WHERE clip_id=?',(body['jobId'],)).fetchone()[0]==original
        assert db.execute('SELECT token FROM candidate_previews WHERE job_id=?',(body['jobId'],)).fetchone()[0]=='b'*64
