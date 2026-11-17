import json
from types import SimpleNamespace as NS
import pytest
from fastapi.testclient import TestClient
from test_customer_analysis_release import ready_customer
from test_analysis import local_preferences


def test_customer_personalization_applies_only_consented_counts_and_selected_focus(tmp_path,monkeypatch):
    (store,uid,app,messages,*_),body,headers=ready_customer(tmp_path,monkeypatch)
    store.save_preferences(uid,{'usagePreset':'balanced','focus':'gameplay','avoid':'all','approval':'review'})
    state=app.state.davey.save(uid,{**app.state.davey.settings(uid),'personalContext':True})
    captured=[];original=messages.create
    def create(**kwargs):captured.append(json.loads(kwargs['messages'][0]['content']));return original(**kwargs)
    messages.create=create
    body={**body,'personalPreferences':local_preferences(),'personalPreferencesRevision':state['revision']}
    with TestClient(app) as client:response=client.post('/api/worker/analyze',json=body,headers=headers)
    assert response.status_code==200
    assert captured[0]['feedbackPreferences']['approveReasons']=={'Funny':2}
    assert captured[0]['context']['selectionPreferences']=={'focus':'gameplay','avoid':'all'}
    assert response.json()['personalContextUsed'] is True
    with store.connection() as db:
        run=dict(db.execute('SELECT * FROM analysis_runs WHERE user_id=?',(uid,)).fetchone())
        assert 'Funny' not in json.dumps(run) and run['personal_context_used']==1
    assert messages.calls==1


@pytest.mark.parametrize('change',['no_consent','missing_revision','stale_revision','revoke_during_count','focus_during_count','pause_during_count'])
def test_revoked_or_changed_personal_context_never_reaches_paid_dispatch(tmp_path,monkeypatch,change):
    (store,uid,app,messages,*_),body,headers=ready_customer(tmp_path,monkeypatch)
    settings=app.state.davey.settings(uid)
    state=app.state.davey.save(uid,{**settings,'personalContext':True}) if change!='no_consent' else app.state.davey.status(uid)
    body={**body,'personalPreferences':local_preferences(),'personalPreferencesRevision':state['revision']}
    if change=='missing_revision':body.pop('personalPreferencesRevision')
    elif change=='stale_revision':body['personalPreferencesRevision']+=1
    elif change.endswith('during_count'):
        def count(**kwargs):
            if change=='revoke_during_count':app.state.davey.save(uid,{**app.state.davey.settings(uid),'personalContext':False})
            elif change=='focus_during_count':store.save_preferences(uid,{'usagePreset':'balanced','focus':'humor','avoid':'personal'})
            else:store.save_preferences(uid,{'usagePreset':'paused','focus':'balanced','avoid':'personal'})
            return NS(input_tokens=100)
        messages.count_tokens=count
    with TestClient(app) as client:response=client.post('/api/worker/analyze',json=body,headers=headers)
    assert response.status_code==409
    assert messages.calls==0
    assert app.state.ledger.snapshot(uid)['reservedMicros']==0


def test_reason_count_cannot_exceed_confirmed_review_count():
    from server.analysis import validate_personal_preferences,AnalysisDenied
    with pytest.raises(AnalysisDenied):validate_personal_preferences({'schemaVersion':1,'reviewCount':1,'approveReasons':{'Funny':2},'rejectReasons':{}})


def test_structured_safety_metadata_and_selection_modes_are_explicit():
    from server.analysis import SYSTEM,OUTPUT_CONFIG,validate_candidate,AnalysisDenied
    fields=OUTPUT_CONFIG['format']['schema']['anyOf'][0]
    assert 'selectionPreferences' in SYSTEM and 'safetyFlags' in fields['required']
    candidate={'start':0,'end':20,'score':95,'title':'Moment','caption':'Caption','rationale':'Evidence'}
    assert 'safetyFlags' not in validate_candidate(candidate,30)  # old manual-only cache
    assert validate_candidate({**candidate,'safetyFlags':[]},30)['safetyFlags']==[]
    for flags in ['safe',[True],['execute_code'],['private_information']*2]:
        with pytest.raises(AnalysisDenied):validate_candidate({**candidate,'safetyFlags':flags},30)
