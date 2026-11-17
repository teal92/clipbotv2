import json, time
from datetime import datetime, timezone
from types import SimpleNamespace
import pytest
from server.store import Store
from server.dashboard_metrics import aggregate_dashboard
from server.provider_analytics import ProviderAnalytics

def epoch(value): return datetime.fromisoformat(value).replace(tzinfo=timezone.utc).timestamp()

@pytest.fixture
def store(tmp_path): return Store(tmp_path/'metrics.db')

def test_reviews_bucket_actual_timestamp_and_preserve_undated_history(store):
    with store.connection() as db:
        for uid, cid, at, decision in [('u','a',epoch('2026-10-12T23:30'),'approve'),('u','b',None,'reject'),('other','c',epoch('2026-10-13T01:00'),'approve')]:
            db.execute('INSERT INTO reviews VALUES(?,?,?)',(uid,cid,json.dumps({'reviewedAt':at,'user_feedback':{'decision':decision}})))
    value=aggregate_dashboard(store,'u','day','America/New_York',epoch('2026-10-13T02:00'))
    assert value['totals']['approved']==1 and value['totals']['denied']==1
    assert value['totals']['undatedReviews']==1
    assert value['buckets'][19]['approved']==1
    assert sum(b['denied'] for b in value['buckets'])==0
    with pytest.raises(ValueError):aggregate_dashboard(store,'u',timezone_name='../etc')

def fake_oauth(records, request):
    return SimpleNamespace(vault=SimpleNamespace(load=lambda uid,p:records.get((uid,p))),request=request,version='v24.0')

def account_record(scopes=('video.list',)):
    return {'profile':{'id':'owner','name':'Account'},'tokens':{'access_token':'SECRET','expires_at':time.time()+3600,'scopes':list(scopes)},'_version':'encrypted'}

def test_views_are_collected_persisted_cached_and_owner_scoped(store):
    calls=[]
    def request(method,url,**kwargs):
        calls.append((method,url))
        if 'list' in url:return {'error':{'code':'ok'},'data':{'videos':[{'id':'123'}],'has_more':False,'cursor':0}}
        return {'error':{'code':'ok'},'data':{'videos':[{'id':'123','view_count':42}]}}
    service=ProviderAnalytics(store,fake_oauth({('u','tiktok'):account_record()},request))
    key=service.snapshot('u')['accounts'][0]['accountKey']
    result=service.refresh('u',key)
    assert result['views']==42 and result['status']=='available'
    assert len(calls)==2
    assert service.refresh('u',key)['views']==42 and len(calls)==2
    assert ProviderAnalytics(store,service.oauth).snapshot('u')['totalViews']==42
    assert service.snapshot('other')['totalViews'] is None
    assert 'SECRET' not in json.dumps(service.snapshot('u'))
    with pytest.raises(ValueError):service.refresh('other',key)

def test_missing_permissions_empty_metrics_and_provider_errors_are_not_zero(store):
    service=ProviderAnalytics(store,fake_oauth({('u','tiktok'):account_record(())},lambda *a,**k:pytest.fail('No request without scope')))
    account=service.snapshot('u')['accounts'][0]
    assert account['views'] is None and account['status']=='permission_required'
    assert service.refresh('u',account['accountKey'])['views'] is None
    service.oauth=fake_oauth({('u','tiktok'):account_record()},lambda *a,**k: {'error':{'code':'ok'},'data':{'videos':[{'id':'123'}],'has_more':False}})
    value=service.refresh('u',account['accountKey'])
    assert value['views'] is None and value['status']=='unavailable'

def test_cursor_never_follows_provider_url_and_partial_is_explicit(store):
    calls=[]
    def request(method,url,**kwargs):
        calls.append(url)
        if 'list' in url:return {'error':{'code':'ok'},'data':{'videos':[{'id':'123'}],'has_more':True,'cursor':12345},'paging':{'next':'https://evil.test/token'}}
        return {'error':{'code':'ok'},'data':{'videos':[{'id':'123','view_count':9}]}}
    service=ProviderAnalytics(store,fake_oauth({('u','tiktok'):account_record()},request))
    value=service.refresh('u',service.snapshot('u')['accounts'][0]['accountKey'])
    assert value['status']=='partial' and value['views']==9
    assert service.snapshot('u')['totalViews'] is None
    assert all(url.startswith('https://open.tiktokapis.com/') for url in calls)

def test_posting_streak_uses_verified_publication_local_day_not_attempt_day(store):
    with store.connection() as db:
        db.execute('CREATE TABLE publications(user_id TEXT,status TEXT,receipt TEXT,updated REAL)')
        for uid,status,at in [('u','published',epoch('2026-10-13T02:00')),('u','published',epoch('2026-10-12T02:00')),('u','uploading',epoch('2026-10-13T15:00')),('other','published',epoch('2026-10-13T15:00'))]:
            db.execute('INSERT INTO publications VALUES(?,?,?,?)',(uid,status,json.dumps({'verifiedAt':at}),epoch('2026-10-13T15:00')))
    value=aggregate_dashboard(store,'u','week','America/New_York',epoch('2026-10-13T20:00'))
    assert value['postingStreak']==2 and value['streakPostedToday'] is False
    assert value['totals']['posts']==2
    assert [row['posts'] for row in value['buckets']][-3:]==[1,1,0]

def test_reconnect_or_revocation_hides_previous_cache(store):
    records={('u','tiktok'):account_record()}
    def request(method,url,**kwargs):
        return {'error':{'code':'ok'},'data':{'videos':[{'id':'123','view_count':12}],'has_more':False}}
    service=ProviderAnalytics(store,fake_oauth(records,request));key=service.snapshot('u')['accounts'][0]['accountKey']
    assert service.refresh('u',key)['views']==12
    records[('u','tiktok')]['_version']='new-account-authorization'
    assert service.snapshot('u')['accounts'][0]['views'] is None
    records.clear()
    assert service.snapshot('u')['accounts']==[]

def test_meta_actual_metric_zero_and_missing_metric_are_distinct(store):
    record={'profile':{'id':'owner'},'tokens':{'expires_at':time.time()+3600,'scopes':['instagram_manage_insights'],'destinations':[{'id':'111','name':'IG','access_token':'SECRET'}]},'_version':'encrypted'}
    calls=[]
    def request(method,url,**kwargs):
        calls.append((method,url,kwargs))
        if url.endswith('/media'):return {'data':[{'id':'123','media_type':'VIDEO'}]}
        return {'data':[{'name':'views','values':[{'value':0}]}]}
    service=ProviderAnalytics(store,fake_oauth({('u','instagram'):record},request))
    value=service.refresh('u',service.snapshot('u')['accounts'][0]['accountKey'])
    assert value['status']=='available' and value['views']==0
    assert all(method=='GET' and url.startswith('https://graph.facebook.com/v24.0/') for method,url,_ in calls)
    assert calls[-1][2]['params']=={'metric':'views'}

def test_provider_failure_is_sanitized_and_backed_off(store):
    calls=[]
    def request(*args,**kwargs):calls.append(1);raise RuntimeError('SECRET https://evil.test/private')
    service=ProviderAnalytics(store,fake_oauth({('u','tiktok'):account_record()},request));key=service.snapshot('u')['accounts'][0]['accountKey']
    assert service.refresh('u',key)['status']=='unavailable'
    assert service.refresh('u',key)['views'] is None and len(calls)==1
    assert 'SECRET' not in json.dumps(service.snapshot('u'))

def test_scan_resumes_cursor_and_does_not_double_count_same_video(store):
    calls=[]
    def request(method,url,**kwargs):
        calls.append(kwargs)
        if url.endswith('/list/'):
            return {'error':{'code':'ok'},'data':{'videos':[{'id':'123'}],'has_more':kwargs['json'].get('cursor') is None,'cursor':12345}}
        return {'error':{'code':'ok'},'data':{'videos':[{'id':'123','view_count':10}]}}
    service=ProviderAnalytics(store,fake_oauth({('u','tiktok'):account_record()},request));key=service.snapshot('u')['accounts'][0]['accountKey']
    assert service.refresh('u',key)['status']=='partial'
    with store.connection() as db:db.execute('UPDATE dashboard_view_cache SET updated=0')
    value=service.refresh('u',key)
    assert value['status']=='available' and value['views']==10
    assert calls[2]['json']['cursor']==12345
