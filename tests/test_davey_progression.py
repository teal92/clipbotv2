import importlib.util,json
import pytest
from server.store import Store


@pytest.fixture
def setup(tmp_path):
    assert importlib.util.find_spec('server.davey') is not None, 'Server-owned Davey progression is missing'
    from server.davey import DaveyStore
    store=Store(tmp_path/'davey.db')
    uid=store.create_user('one@example.test','LongPassword!2026','one')
    other=store.create_user('two@example.test','LongPassword!2026','two')
    return store,uid,other,DaveyStore(store)


def decisions(store,uid,count,start=0,actor='human'):
    with store.connection() as db:
        for index in range(start,start+count):
            cid=f'{index:032x}';candidate={'id':cid,'score':95,'title':'A complete moment','caption':'A clear caption','rationale':'Transcript evidence','start':0,'end':20,'safetyFlags':[]}
            db.execute('INSERT OR REPLACE INTO candidates VALUES(?,?,?)',(cid,uid,json.dumps(candidate)))
            db.execute('INSERT OR REPLACE INTO reviews VALUES(?,?,?)',(uid,cid,json.dumps({'actor':actor,'candidate':candidate,'user_feedback':{'decision':'approve','reasons':[],'justification':''}})))


def policy(davey,uid,**changes):
    return {**davey.settings(uid),**changes}


def validation(store,uid,davey,positive=20,positive_correct=19,negative=5,negative_correct=4,start=1000):
    # Each candidate exists before its prediction and its first human decision.
    for index in range(positive+negative):
        cid=f'{start+index:032x}';approve=index<positive
        candidate={'id':cid,'score':95 if approve else 80,'title':'A complete moment','caption':'A clear caption','rationale':'Transcript evidence','start':0,'end':20,'safetyFlags':[]}
        with store.connection() as db:db.execute('INSERT INTO candidates VALUES(?,?,?)',(cid,uid,json.dumps(candidate)))
        davey.prediction(uid,cid,candidate,davey.context_key(uid))
        correct=index<positive_correct if approve else index-positive<negative_correct
        choice=('approve' if approve else 'reject') if correct else ('reject' if approve else 'approve')
        store.save_review(uid,cid,choice,[],'',local_learning=True)
        with store.connection(atomic=True) as db:davey.evaluate(db,uid,cid,choice)


def test_phase_boundaries_and_automatic_decisions_do_not_teach(setup):
    store,uid,other,davey=setup
    assert davey.status(uid)['phase']==1 and davey.settings(uid)['personalContext'] is False
    decisions(store,uid,1);assert davey.status(uid)['phase']==2
    decisions(store,uid,98,start=1);assert davey.status(uid)['phase']==2
    decisions(store,uid,100,start=100,actor='davey');assert davey.status(uid)['manualDecisions']==99
    decisions(store,uid,1,start=99);assert davey.status(uid)['phase']==3
    assert davey.status(other)['phase']==1


def test_phase_four_requires_real_validation_and_explicit_opt_in(setup):
    store,uid,_,davey=setup;decisions(store,uid,100)
    davey.save(uid,policy(davey,uid,personalContext=True,shadowEnabled=True))
    validation(store,uid,davey)
    status=davey.status(uid)
    assert status['phase']==4 and status['qualified'] is True
    assert status['validation']=={'decisions':25,'agreement':92,'predictedApprovals':20,'approvalPrecision':95}
    assert davey.settings(uid)['automatic'] is False
    # No real destination/live switch is enabled merely by qualifying.
    assert status['automaticEnabled'] is False


@pytest.mark.parametrize('positive,correct,negative,negative_correct',[(20,19,4,4),(19,19,6,6),(20,18,5,5),(20,19,5,3)])
def test_insufficient_or_inaccurate_validation_cannot_unlock(setup,positive,correct,negative,negative_correct):
    store,uid,_,davey=setup;decisions(store,uid,100)
    davey.save(uid,policy(davey,uid,personalContext=True,shadowEnabled=True))
    validation(store,uid,davey,positive,correct,negative,negative_correct)
    assert davey.status(uid)['phase']==3
    with pytest.raises(ValueError):davey.save(uid,policy(davey,uid,automatic=True,rightsAccepted=True,platforms=['instagram'],sources=[{'platform':'twitch','login':'channel'}]))


def test_preference_changes_invalidate_qualification_but_not_ordinary_new_feedback(setup):
    store,uid,_,davey=setup;decisions(store,uid,100)
    davey.save(uid,policy(davey,uid,personalContext=True,shadowEnabled=True));validation(store,uid,davey)
    decisions(store,uid,1,start=5000);assert davey.status(uid)['phase']==4
    store.save_preferences(uid,{'focus':'gameplay','avoid':'personal'})
    assert davey.status(uid)['phase']==3
    store.save_preferences(uid,{'focus':'balanced','avoid':'personal'})
    assert davey.status(uid)['phase']==3


def test_repeated_or_edited_decisions_cannot_rewrite_first_validation_result(setup):
    store,uid,_,davey=setup;decisions(store,uid,100)
    davey.save(uid,policy(davey,uid,personalContext=True,shadowEnabled=True))
    validation(store,uid,davey)
    first=davey.status(uid)['validation']
    for _ in range(3):store.save_review(uid,f'{1000:032x}','reject',[],'',local_learning=True)
    assert davey.status(uid)['validation']==first


@pytest.mark.parametrize('changes',[{'phase':4},{'dailyPostLimit':True},{'dailyPostLimit':1000},{'platforms':['tiktok']},{'sources':[{'platform':'twitch','login':'a;run'}]},{'personalContext':'yes'},{'shadowEnabled':True},{'automatic':True}])
def test_hidden_or_malformed_settings_fail_closed(setup,changes):
    _,uid,_,davey=setup
    with pytest.raises(ValueError):davey.save(uid,policy(davey,uid,**changes))


def test_progression_api_requires_owner_session_csrf_and_current_revision(setup):
    from fastapi.testclient import TestClient
    from server.app import create_app
    store,uid,other,_=setup;app=create_app(store,origin='http://testserver')
    with TestClient(app) as client:
        assert client.get('/api/davey/progression').status_code==401
        raw,csrf=store.new_session(uid);client.cookies.set('clipbot_session',raw)
        state=client.get('/api/davey/progression').json()
        assert state['phase']==1 and state['revision']==0
        values={**state['settings'],'personalContext':True}
        body={'settings':values,'revision':0}
        assert client.put('/api/davey/progression',json=body,headers={'Origin':'http://testserver'}).status_code==403
        headers={'Origin':'http://testserver','X-CSRF-Token':csrf}
        saved=client.put('/api/davey/progression',json=body,headers=headers)
        assert saved.status_code==200 and saved.json()['revision']==1
        assert client.put('/api/davey/progression',json=body,headers=headers).status_code==409
        assert client.put('/api/davey/progression',json={**body,'userId':other},headers=headers).status_code==422
        assert app.state.davey.settings(other)['personalContext'] is False
        assert client.get('/api/workspace').json()['davey']['revision']==1
        token=store.connect_worker(store.new_pairing(uid))
        worker=client.get('/api/worker/state',headers={'Authorization':'Bearer '+token}).json()
        assert worker['davey']['personalContext'] is True and worker['preferences']['approval']=='review'


def test_personal_context_revocation_immediately_turns_off_dependent_features(setup):
    store,uid,_,davey=setup;decisions(store,uid,100)
    enabled=davey.save(uid,policy(davey,uid,personalContext=True,shadowEnabled=True))
    result=davey.save(uid,policy(davey,uid,personalContext=False))
    assert result['revision']>enabled['revision']
    assert result['personalContext'] is False and result['shadowEnabled'] is False
    assert result['settings']['automatic'] is False
