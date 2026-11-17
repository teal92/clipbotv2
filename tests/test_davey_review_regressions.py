import json,time
from datetime import datetime,timezone
import pytest
from fastapi.testclient import TestClient
from test_customer_analysis_release import ready_customer
from test_davey_progression import policy
from test_davey_automation import automatic_customer
from test_analysis import setup,transcript


@pytest.mark.parametrize('boundary',['analysis_counting','analysis_dispatch'])
def test_revoke_at_count_boundary_never_exports_to_token_counter(tmp_path,monkeypatch,boundary):
    (store,uid,app,messages,*_),body,headers=ready_customer(tmp_path,monkeypatch)
    state=store.davey.save(uid,policy(store.davey,uid,personalContext=True))
    from test_analysis import local_preferences
    body.update(personalPreferences=local_preferences(),personalPreferencesRevision=state['revision'])
    original=app.state.analysis.events.emit;counted=[]
    def emit(owner,event,**kwargs):
        if event==boundary:store.davey.save(uid,policy(store.davey,uid,personalContext=False))
        return original(owner,event,**kwargs)
    app.state.analysis.events.emit=emit
    def count(**kwargs):
        from types import SimpleNamespace
        counted.append(kwargs);return SimpleNamespace(input_tokens=100)
    messages.count_tokens=count
    with TestClient(app) as client:assert client.post('/api/worker/analyze',json=body,headers=headers).status_code==409
    assert len(counted)==(0 if boundary=='analysis_counting' else 1) and messages.calls==0


def test_reset_never_reimports_history_or_automatic_feedback(tmp_path,monkeypatch):
    store,uid,app,token,job,headers,calls=automatic_customer(tmp_path,monkeypatch)
    from server.analysis import feedback_preferences
    assert app.state.publication.automation.dispatch(uid,token)['prepared']==1
    store.davey.reset(uid,store.davey.status(uid)['revision'])
    store.davey.save(uid,policy(store.davey,uid,personalContext=True))
    assert feedback_preferences(store,uid)=={'reviewCount':0,'approveReasons':{},'rejectReasons':{}}
    store.save_review(uid,f'{1000:032x}','approve',['Funny'],'',local_learning=True)
    assert feedback_preferences(store,uid)=={'reviewCount':1,'approveReasons':{'Funny':1},'rejectReasons':{}}


def test_final_mutation_rechecks_current_daily_allowance(tmp_path,monkeypatch):
    from server.publication import PublicationDenied
    store,uid,app,token,job,headers,calls=automatic_customer(tmp_path,monkeypatch)
    pub=app.state.publication;assert pub.automation.dispatch(uid,token)['prepared']==1
    attempt=pub.snapshot(uid)[0]['id'];pub.grant(token,attempt)
    day=datetime.now(timezone.utc).strftime('%Y-%m-%d')
    with store.connection() as db:
        for n in range(20):db.execute("INSERT INTO clip_capacity VALUES(?,?,?,'reserved')",(uid,f'{9000+n:032x}',day))
    before=len([1 for method,_ in calls if method=='POST'])
    with pytest.raises(PublicationDenied):pub.uploaded(token,attempt)
    assert len([1 for method,_ in calls if method=='POST'])==before


def test_legacy_settled_cache_recovers_once_without_reanalyzing(setup):
    store,uid,ledger,messages,service=setup
    context={'duration':120,'platform':'twitch','creator':'channel'}
    result=service.analyze(uid,'old-settled',transcript(),context)
    recovered=service.analyze(uid,'old-settled',transcript(),{**context,'selectionPreferences':{'focus':'humor','avoid':'all'}})
    assert recovered==result and messages.calls==1
    with pytest.raises(ValueError):service.analyze(uid,'old-settled',[{'start':0,'end':60,'text':'Changed transcript'}],{**context,'selectionPreferences':{'focus':'humor','avoid':'all'}})
    assert messages.calls==1
