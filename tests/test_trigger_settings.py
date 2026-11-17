import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from server.store import Store
from server.trigger_settings import TriggerStore, default_trigger_settings, validate_trigger_settings, build_trigger_router

@pytest.mark.parametrize('change',[{'beforeSeconds':True},{'beforeSeconds':9},{'afterSeconds':46},{'beforeSeconds':45,'afterSeconds':45},{'cooldownSeconds':301},{'audioEnabled':1},{'audioRiseDb':0},{'chatSpikeMultiplier':21},{'user_id':'other'},{'rules':[{'phrase':'x','source':'url','priority':'high'}]},{'rules':[{'phrase':' ','source':'speech','priority':'high'}]},{'rules':[{'phrase':'x','source':'speech','priority':'high','extra':1}]},{'rules':[{'phrase':'x','source':'speech','priority':'high'}]*21}])
def test_rejects_invalid_settings(change):
    with pytest.raises(ValueError):validate_trigger_settings({**default_trigger_settings(),**change})

def test_persists_per_account_and_enforces_authenticated_owner(tmp_path):
    store=Store(tmp_path/'triggers.db')
    first=store.create_user('a@example.com','long-password-123','A')
    second=store.create_user('b@example.com','long-password-123','B')
    triggers=TriggerStore(store)
    app=FastAPI()
    def current(request,write=False):
        uid=request.headers.get('x-user')
        if uid not in (first,second):raise HTTPException(401,'Sign in required')
        if write and request.headers.get('x-csrf')!='yes':raise HTTPException(403,'CSRF required')
        return {'user_id':uid}
    app.include_router(build_trigger_router(store,current));client=TestClient(app)
    settings={**default_trigger_settings(),'beforeSeconds':30}
    assert client.put('/api/scouts/triggers',json=settings,headers={'x-user':first}).status_code==403
    assert client.put('/api/scouts/triggers',json=settings,headers={'x-user':first,'x-csrf':'yes'}).json()==settings
    assert client.get('/api/scouts/triggers',headers={'x-user':second}).json()==default_trigger_settings()
    assert client.get('/api/scouts/triggers').status_code==401
    assert TriggerStore(store).get(first)==settings
    with pytest.raises(ValueError):triggers.save('missing',settings)
    assert triggers.get(second)==default_trigger_settings()

def test_defaults_do_not_share_mutable_rules():
    first=default_trigger_settings();first['rules'].clear()
    assert len(default_trigger_settings()['rules'])==2

def test_manual_requests_are_bounded_latest_per_source_and_owned(tmp_path):
    store=Store(tmp_path/'manual.db')
    first=store.create_user('first@example.com','long-password-123','First')
    second=store.create_user('second@example.com','long-password-123','Second')
    triggers=TriggerStore(store)
    source={'platform':'twitch','login':'Streamer'}
    old=triggers.request(first,source);latest=triggers.request(first,source)
    assert old['nonce']!=latest['nonce']
    assert triggers.requests(first)==[latest]
    assert latest['login']=='streamer'
    assert triggers.requests(second)==[]
    with pytest.raises(ValueError):triggers.request(first,{**source,'user_id':second})
    with pytest.raises(ValueError):triggers.request(first,{'platform':'twitch','login':'../bad'})
    with store.connection() as db:db.execute('UPDATE scout_trigger_requests SET created=0')
    assert triggers.requests(first)==[]
