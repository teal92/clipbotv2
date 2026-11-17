import time
import httpx,pytest
from server.scouts import ScoutDenied
from server.discovery import Directory
from server.oauth import OAuthUnavailable

class Vault:
    def load(self,uid,platform):
        if uid!='owner':return None
        return {'tokens':{'access_token':'PRIVATE-TOKEN','expires_at':time.time()+3600}}
class OAuth:
    vault=Vault()
    def credentials(self,platform):return 'public-id','PRIVATE-SECRET'
    def rows(self,payload):return payload['data']
    def request(self,method,url,**kwargs):
        assert kwargs['headers']['Authorization']=='Bearer PRIVATE-TOKEN'
        if 'twitch' in url:return {'data':[{'id':'live1','user_login':'livechannel','user_name':'Live','game_id':'42','game_name':'Game','viewer_count':20,'title':'PRIVATE-TOKEN'}]}
        if url.endswith('/channels'):return {'data':[{'slug':'pinned','stream':{'is_live':False},'category':{'id':42,'name':'Game'}}]}
        return {'data':[{'id':'kick1','channel':{'slug':'kicklive'},'category':{'id':42,'name':'Game'},'broadcaster_user':{'username':'Live'},'viewer_count':30}]}

@pytest.mark.parametrize('platform',['twitch','kick'])
def test_directory_preserves_live_source_metadata_without_credentials(platform):
    directory=Directory(OAuth());result=directory.streams('owner',platform,[],[])
    assert result and result[0]['live'] is True and result[0]['categoryId']=='42'
    assert 'PRIVATE' not in str(result)
    assert result[0]['platform']==platform
    with pytest.raises(OAuthUnavailable):directory.streams('other',platform,[],[])

def test_kick_explicit_offline_source_not_invented_live():
    result=Directory(OAuth()).streams('owner','kick',['pinned'],[])
    assert result[0]['login']=='pinned' and result[0]['live'] is False

def test_combined_category_filters_are_discovered_in_bounded_batches(tmp_path,monkeypatch):
 from fastapi.testclient import TestClient
 from server.store import Store
 from server.app import create_app
 from server.scouts import ScoutStore
 calls=[]
 def streams(self,uid,platform,logins,categories):
  assert len(categories)<=25;calls.append((platform,categories));return []
 monkeypatch.setattr(Directory,'streams',streams)
 store=Store(tmp_path/'batched.db');uid=store.create_user('batched@example.com','a-good-long-password','Batch');store.set_coverage(uid,review_daily=45,user_monthly=6000000,scouts=40,favorites=3,categories=25,posts=20)
 forced=[{'platform':'twitch','id':str(i),'name':f'Game {i}'} for i in range(1,26)]
 ScoutStore(store).save(uid,{'running':True,'slots':25,'forced':[],'favorites':[],'forcedCategories':forced,'categories':[{'platform':'twitch','id':'26','name':'Last'}]})
 token=store.connect_worker(store.new_pairing(uid))
 with TestClient(create_app(store,origin='http://testserver')) as client:response=client.get('/api/worker/discovery',headers={'Authorization':'Bearer '+token})
 assert response.status_code==200 and not response.json()['errors']
 assert sorted(len(cats) for platform,cats in calls if platform=='twitch')==[1,25]

def test_kick_hyphenated_names_and_ranked_endpoint_are_supported():
 class RankedOAuth(OAuth):
  def request(self,method,url,**kwargs):
   assert url.endswith('/public/v1/livestreams') and kwargs['params']['sort']=='viewer_count'
   return {'data':[{'slug':'real-kick-name','broadcaster_user_id':42,'viewer_count':10000,'category':{'id':42,'name':'Game'}}]}
 rows=Directory(RankedOAuth()).streams('owner','kick',[],[])
 assert rows[0]['login']=='real-kick-name' and rows[0]['viewers']==10000
 from worker.capture import stream_url
 assert stream_url(rows[0])=='https://kick.com/real-kick-name'
 from server.scouts import source_identity
 with pytest.raises(ScoutDenied):source_identity({'platform':'twitch','login':'bad-name'})

def test_waiting_favorite_category_does_not_hide_automatic_streams(tmp_path,monkeypatch):
 from fastapi.testclient import TestClient
 from server.store import Store
 from server.app import create_app
 from server.scouts import ScoutStore
 def streams(self,uid,platform,logins,categories):
  if platform!='twitch' or categories:return []
  return [{'platform':'twitch','login':'automatic','live':True,'categoryId':'99','viewers':10}]
 monkeypatch.setattr(Directory,'streams',streams)
 store=Store(tmp_path/'waiting.db');uid=store.create_user('waiting@example.com','a-good-long-password','Waiting')
 store.set_coverage(uid,review_daily=45,user_monthly=6000000,scouts=2,favorites=1,categories=1,posts=20)
 ScoutStore(store).save(uid,{'running':True,'slots':2,'forced':[],'favorites':[],'forcedCategories':[{'platform':'twitch','id':'42','name':'Offline game'}],'categories':[]})
 token=store.connect_worker(store.new_pairing(uid))
 with TestClient(create_app(store,origin='http://testserver')) as client:
  response=client.get('/api/worker/discovery',headers={'Authorization':'Bearer '+token})
 assert response.status_code==200
 assert any(row['login']=='automatic' for row in response.json()['sources'])

def test_provider_thumbnails_are_sized_and_restricted_to_exact_cdn_hosts():
 from server.discovery import thumbnail_url
 assert thumbnail_url('twitch','https://static-cdn.jtvnw.net/previews/live-{width}x{height}.jpg')=='https://static-cdn.jtvnw.net/previews/live-320x180.jpg'
 assert thumbnail_url('kick','https://images.kick.com/preview.webp')
 for bad in ('https://images.kick.com.evil.test/a','http://images.kick.com/a','https://secret@images.kick.com/a','https://images.kick.com:8000/a','https://images.kick.com/a#secret'):
  assert thumbnail_url('kick',bad) is None


def test_kick_channel_lookup_reads_nested_live_viewers():
    row={'slug':'livechannel','stream':{'is_live':True,'viewer_count':4321},'category':{'id':42,'name':'Game'}}
    assert Directory.normalized('kick',row,True)['viewers']==4321
    row['stream']['viewer_count']=0
    assert Directory.normalized('kick',row,True)['viewers']==0

def test_category_coverage_returns_three_ranked_streams_per_category_and_caches(monkeypatch):
    directory=Directory(OAuth());calls=[]
    def streams(uid,platform,logins,categories):
        calls.append((uid,platform,tuple(categories)))
        return [{'platform':platform,'login':f'stream{i}','live':True,'categoryId':categories[0],'viewers':i} for i in range(5)]
    monkeypatch.setattr(directory,'streams',streams)
    first=directory.category_coverage('owner','twitch',['1','2'])
    assert [r['viewers'] for r in first['sources']]==[4,3,2,4,3,2]
    assert first['errors']=={} and len(calls)==2
    assert directory.category_coverage('owner','twitch',['1','2'])==first and len(calls)==2
    with pytest.raises(ScoutDenied):directory.category_coverage('owner','twitch',[str(i) for i in range(11)])
    with pytest.raises(ScoutDenied):directory.category_coverage('owner','twitch',['../secret'])
    with pytest.raises(OAuthUnavailable):directory.category_coverage('other','twitch',['1','2'])

def test_category_coverage_partial_errors_and_concurrency_are_bounded(monkeypatch):
    import threading
    directory=Directory(OAuth());lock=threading.Lock();active=0;maximum=0
    def streams(uid,platform,logins,categories):
        nonlocal active,maximum
        with lock:active+=1;maximum=max(maximum,active)
        try:
            time.sleep(.01)
            if categories[0]=='2':raise OAuthUnavailable('PRIVATE-TOKEN')
            return [{'platform':platform,'login':'real','live':True,'categoryId':categories[0],'viewers':4}]
        finally:
            with lock:active-=1
    monkeypatch.setattr(directory,'streams',streams)
    result=directory.category_coverage('owner','kick',[str(i) for i in range(10)])
    assert len(result['sources'])==9 and maximum<=4
    assert '2' in result['errors'] and 'PRIVATE' not in str(result)
