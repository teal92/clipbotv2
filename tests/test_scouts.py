import pytest
from server.store import Store
from server.scouts import ScoutStore, ScoutDenied
from worker.scout_scheduler import select_sources

@pytest.fixture
def setup(tmp_path):
    store=Store(tmp_path/'scouts.db'); uid=store.create_user('scouts@example.com','a-good-long-password','Scout')
    store.set_coverage(uid,review_daily=45,user_monthly=6000000,scouts=3,favorites=2,categories=1,posts=20)
    return store,uid,ScoutStore(store)

def source(login,live=True,category='game'):
    return {'platform':'twitch','login':login,'live':live,'categoryId':category}

def config():
    return {'running':True,'slots':3,'forced':[{'platform':'twitch','login':'pinned'}],'favorites':[{'platform':'twitch','login':'favorite'}],'categories':[{'platform':'twitch','id':'game','name':'Game'}]}

def test_source_priority_offline_dedup_and_rotation():
    cfg=config(); live=[source('favorite'),source('normal'),source('pinned'),source('pinned'),source('offline',False),source('another')]
    assert [s['login'] for s in select_sources(cfg,live,3)]==['pinned','favorite','another']
    cfg['forced']=[{'platform':'twitch','login':'offline'}]
    assert len(select_sources(cfg,live,3))==3
    assert 'offline' not in [s['login'] for s in select_sources(cfg,live,3)]
    assert select_sources({**cfg,'running':False},live,3)==[]
    assert len(select_sources(cfg,live,1))==1
    cfg['forced']=[{'platform':'twitch','login':'favorite'}]
    assert len({s['login'] for s in select_sources(cfg,live,3)})==3

def test_saved_scouts_are_owned_and_limit_checked(setup):
    store,uid,scouts=setup; scouts.save(uid,config())
    assert scouts.snapshot(uid)['configuration']['running']
    assert scouts.snapshot('other')['configuration']['favorites']==[]
    for bad in [{**config(),'slots':4},{**config(),'slots':True},{**config(),'forced':[{'platform':'twitch','login':str(i)} for i in range(4)]},{**config(),'favorites':[{'platform':'twitch','login':str(i)} for i in range(3)]},{**config(),'user_id':'other'}]:
        with pytest.raises(ScoutDenied):scouts.save(uid,bad)
    with pytest.raises(ScoutDenied):scouts.save('other',config())
    store.set_coverage(uid,review_daily=45,user_monthly=6000000,scouts=1,favorites=0,categories=0,posts=20)
    snap=scouts.snapshot(uid)
    assert snap['effective']['slots']==1 and snap['effective']['favorites']==[]

@pytest.mark.parametrize('login',['../secret','a;echo','https://evil.test','', 'x'*40])
def test_untrusted_source_identifiers_rejected(setup,login):
    store,uid,scouts=setup
    with pytest.raises(ScoutDenied):scouts.save(uid,{**config(),'forced':[{'platform':'twitch','login':login}]})

def test_popularity_and_forced_category_reserves_its_top_streamer():
 cfg={'running':True,'slots':2,'forced':[],'favorites':[],'categories':[],'forcedCategories':[{'platform':'twitch','id':'42','name':'Game'}]}
 live=[{**source('low',category='42'),'viewers':10},{**source('outside',category='9'),'viewers':1000},{**source('best',category='42'),'viewers':100}]
 assert [v['login'] for v in select_sources(cfg,live,2)]==['best','outside']
 cfg['forcedCategories']=[]
 assert [v['login'] for v in select_sources(cfg,live,2)]==['outside','best']

def test_controls_are_owned_and_validate_bounds(setup):
 from server.scouts import default_controls
 store,uid,scouts=setup;controls={**default_controls(),'sensitivity':'strict','captureSeconds':180,'minClipSeconds':30}
 scouts.save_controls(uid,controls);assert scouts.snapshot(uid)['controls']==controls
 assert scouts.controls('other')==default_controls()
 for invalid in [{**controls,'captureSeconds':True},{**controls,'maxClipSeconds':75},{**controls,'minClipSeconds':60,'maxClipSeconds':30},{**controls,'sensitivity':'anything'},{**controls,'captureSeconds':500}]:
  with pytest.raises(ScoutDenied):scouts.save_controls(uid,invalid)
 with pytest.raises(ScoutDenied):scouts.save(uid,{**config(),'forcedCategories':[{'platform':'twitch','id':'42','name':'Game'}]*3})


def test_platform_allocations_enforced_and_zero_disables(setup):
 store,uid,scouts=setup
 cfg={**config(),'categories':[],'platformSlots':{'twitch':2,'kick':1}}
 assert scouts.save(uid,cfg)['configuration']['platformSlots']==cfg['platformSlots']
 live=[source('pinned'),source('favorite'),source('normal'),{**source('kickone'),'platform':'kick','viewers':100}]
 chosen=select_sources(cfg,live,3)
 assert sum(v['platform']=='twitch' for v in chosen)==2
 assert sum(v['platform']=='kick' for v in chosen)==1
 assert all(v['platform']=='twitch' for v in select_sources({**cfg,'platformSlots':{'twitch':3,'kick':0}},live,3))
 for allocation in [{'twitch':3,'kick':3},{'twitch':True,'kick':2},{'twitch':-1,'kick':4}]:
  with pytest.raises(ScoutDenied):scouts.save(uid,{**cfg,'platformSlots':allocation})
