from fastapi.testclient import TestClient
from test_davey_progression import setup,policy
from server.app import create_app


def test_combined_preferences_and_consent_are_atomic_and_revision_checked(setup):
    store,uid,_,_=setup;app=create_app(store,origin='http://testserver')
    session,csrf=store.new_session(uid)
    with TestClient(app) as client:
        client.cookies.set('clipbot_session',session)
        headers={'Origin':'http://testserver','X-CSRF-Token':csrf}
        body={'focus':'gameplay','avoid':'all','usagePreset':'balanced','approval':'review','progression':{'revision':0,'settings':policy(store.davey,uid,personalContext=True)}}
        response=client.put('/api/davey',json=body,headers=headers)
        assert response.status_code==200
        assert store.get_preferences(uid)['focus']=='gameplay'
        assert store.davey.settings(uid)['personalContext'] is True
        body['focus']='humor'
        assert client.put('/api/davey',json=body,headers=headers).status_code==409
        assert store.get_preferences(uid)['focus']=='gameplay'
        body['progression']['revision']=store.davey.status(uid)['revision']
        body['progression']['settings']['shadowEnabled']=True
        assert client.put('/api/davey',json=body,headers=headers).status_code==409
        assert store.get_preferences(uid)['focus']=='gameplay'


def test_reset_requires_confirmation_revokes_and_invalidates_without_erasing_history(setup):
    from test_davey_progression import decisions,validation
    store,uid,_,_=setup;app=create_app(store,origin='http://testserver');davey=store.davey
    decisions(store,uid,100);davey.save(uid,policy(davey,uid,personalContext=True,shadowEnabled=True));validation(store,uid,davey)
    session,csrf=store.new_session(uid)
    with TestClient(app) as client:
        client.cookies.set('clipbot_session',session);headers={'Origin':'http://testserver','X-CSRF-Token':csrf}
        state=davey.status(uid);body={'revision':state['revision'],'confirmed':True}
        assert client.post('/api/davey/reset',json=body).status_code==403
        assert client.post('/api/davey/reset',json={**body,'confirmed':False},headers=headers).status_code in (409,422)
        response=client.post('/api/davey/reset',json=body,headers=headers)
        assert response.status_code==200
        assert davey.status(uid)['validation']['decisions']==0
        assert davey.status(uid)['manualDecisions']==125
        assert davey.settings(uid)['personalContext'] is False
        assert response.json()['memoryResetAt']>0


def test_reset_clears_only_bound_local_memory_once(tmp_path):
    from worker.personal_memory import PersonalMemory
    memory=PersonalMemory(tmp_path,'https://clipbot.example','a'*32)
    memory.record('b'*32,'approve',['Funny'],'Private');memory.confirm([{'candidateId':'b'*32,'decision':'approve'}])
    memory.apply_reset(123)
    assert memory.summary()['reviewCount']==0 and memory.review('b'*32) is None
    memory.record('c'*32,'reject',[],'New note')
    memory.apply_reset(123)
    assert memory.review('c'*32)['justification']=='New note'
