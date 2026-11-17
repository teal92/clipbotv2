import json,time
from urllib.parse import urlsplit,parse_qs
import pytest,httpx
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from server.store import Store,token_hash
from server.oauth_store import OAuthVault,OAuthInvalid
from server.oauth import OAuthService,OAuthUnavailable
from server.app import create_app

@pytest.fixture
def setup(tmp_path,monkeypatch):
    monkeypatch.setenv('CLIPBOT_TOKEN_ENCRYPTION_KEY',Fernet.generate_key().decode())
    for name in ['TWITCH_CLIENT_ID','KICK_CLIENT_ID','TIKTOK_CLIENT_KEY','META_APP_ID']:monkeypatch.setenv(name,'public-app-id')
    for name in ['TWITCH_CLIENT_SECRET','KICK_CLIENT_SECRET','TIKTOK_CLIENT_SECRET','META_APP_SECRET']:monkeypatch.setenv(name,'private-app-secret')
    monkeypatch.setenv('META_GRAPH_VERSION','v24.0')
    store=Store(tmp_path/'oauth.db');uid=store.create_user('one@example.com','a-good-long-password','One')
    raw,_=store.new_session(uid);session=store.session(raw)
    return store,uid,raw,session

def test_state_single_use_bound_to_cookie_session_provider_and_expiry(setup):
    store,uid,raw,session=setup;vault=OAuthVault(store)
    state,cookie= vault.begin(session,'kick','verifier-secret')
    with pytest.raises(OAuthInvalid):vault.consume('twitch',state,cookie)
    with pytest.raises(OAuthInvalid):vault.consume('kick',state,'wrong-cookie')
    row=vault.consume('kick',state,cookie)
    assert row['user_id']==uid and row['verifier']=='verifier-secret'
    with pytest.raises(OAuthInvalid):vault.consume('kick',state,cookie)
    state,cookie=vault.begin(session,'kick','other')
    store.logout(raw)
    with pytest.raises(OAuthInvalid):vault.consume('kick',state,cookie)

def test_expiry_encryption_and_account_isolation(setup):
    store,uid,raw,session=setup;vault=OAuthVault(store)
    state,cookie=vault.begin(session,'twitch','secret-verifier')
    with store.connection() as db:db.execute('UPDATE oauth_states SET expires=0')
    with pytest.raises(OAuthInvalid):vault.consume('twitch',state,cookie)
    vault.save(uid,'twitch',{'access_token':'SECRET-ACCESS','refresh_token':'SECRET-REFRESH','expires_at':time.time()+300},{'id':'42','name':'Streamer'})
    assert vault.load(uid,'twitch')['tokens']['access_token']=='SECRET-ACCESS'
    assert vault.load('another-user','twitch') is None
    with store.connection() as db:
        row=db.execute('SELECT * FROM oauth_accounts').fetchone()
        assert 'SECRET-ACCESS' not in str(dict(row)) and 'SECRET-REFRESH' not in str(dict(row))
        db.execute('UPDATE oauth_accounts SET user_id=?',('another-user',))
    with pytest.raises(OAuthInvalid):vault.load('another-user','twitch')

def test_fixed_authorization_urls_and_pkce(setup):
    store,uid,raw,session=setup;service=OAuthService(store,'https://clipbot.example')
    for platform,host in [('twitch','id.twitch.tv'),('kick','id.kick.com'),('tiktok','www.tiktok.com'),('instagram','www.facebook.com'),('facebook','www.facebook.com')]:
        url,cookie=service.start(session,platform)
        assert urlsplit(url).hostname==host
        params=parse_qs(urlsplit(url).query)
        assert params['redirect_uri']==[f'https://clipbot.example/api/connections/{platform}/callback']
        assert 'private-app-secret' not in url
        assert params['state'] and cookie
        if platform=='kick':assert params['code_challenge_method']==['S256']
        if platform in ('facebook','instagram'):
            scopes=set(params['scope'][0].split(','))
            assert 'business_management' in scopes
            assert not scopes.intersection({'ads_read','ads_management','pages_manage_ads'})

def twitch_transport(request):
    if request.url.path=='/oauth2/token':return httpx.Response(200,json={'access_token':'SECRET-ACCESS','refresh_token':'SECRET-REFRESH','expires_in':3600,'scope':[]})
    if request.url.path=='/oauth2/validate':return httpx.Response(200,json={'client_id':'public-app-id','user_id':'42','scopes':[],'expires_in':3600})
    if request.url.path=='/helix/users':return httpx.Response(200,json={'data':[{'id':'42','display_name':'Streamer'}]})
    return httpx.Response(400,json={})

def test_callback_no_strict_session_cookie_needed_and_no_tokens_exposed(setup):
    store,uid,raw,session=setup
    service=OAuthService(store,'https://clipbot.example',transport=httpx.MockTransport(twitch_transport))
    with TestClient(create_app(store,origin='https://clipbot.example',oauth=service),base_url='https://clipbot.example') as client:
        client.cookies.set('clipbot_session',raw)
        headers={'Origin':'https://clipbot.example','X-CSRF-Token':session['csrf']}
        response=client.post('/api/connections/twitch/start',json={'accountType':'personal'},headers=headers)
        assert response.status_code==200
        state=parse_qs(urlsplit(response.json()['authorizationUrl']).query)['state'][0]
        client.cookies.delete('clipbot_session')
        callback=client.get('/api/connections/twitch/callback',params={'code':'provider-code','state':state},follow_redirects=False)
        assert callback.status_code==303 and 'result=connected' in callback.headers['location']
        assert 'SECRET' not in callback.text+str(callback.headers)
        client.cookies.set('clipbot_session',raw)
        status=client.get('/api/connections').json()['platforms'][0]
        assert status['connected'] and status['accountName']=='Streamer' and not status['publishingReady']
        assert 'SECRET' not in json.dumps(status)
        replay=client.get('/api/connections/twitch/callback',params={'code':'provider-code','state':state},follow_redirects=False)
        assert 'result=failed' in replay.headers['location']

def test_failed_provider_does_not_save_or_expose_response(setup):
    store,uid,raw,session=setup
    service=OAuthService(store,'https://clipbot.example',transport=httpx.MockTransport(lambda r:httpx.Response(400,json={'error':'SECRET-ERROR'})))
    url,cookie=service.start(session,'twitch');state=parse_qs(urlsplit(url).query)['state'][0]
    with pytest.raises(OAuthUnavailable) as exc:service.callback('twitch',state,cookie,'code')
    assert 'SECRET' not in str(exc.value)
    assert service.vault.load(uid,'twitch') is None


def test_disconnect_and_new_attempt_invalidate_inflight_saves(setup):
    store,uid,raw,session=setup;vault=OAuthVault(store)
    state,cookie=vault.begin(session,'twitch','')
    flow=vault.consume('twitch',state,cookie)
    vault.disconnect(uid,'twitch')
    with pytest.raises(OAuthInvalid):vault.save(uid,'twitch',{}, {},flow)
    state,cookie=vault.begin(session,'twitch','')
    flow=vault.consume('twitch',state,cookie)
    vault.begin(session,'twitch','')
    with pytest.raises(OAuthInvalid):vault.save(uid,'twitch',{}, {},flow)
    vault.save(uid,'twitch',{'access_token':'old'},{'id':'42','name':'One'})
    snapshot=vault.load(uid,'twitch')
    vault.disconnect(uid,'twitch')
    with pytest.raises(OAuthInvalid):vault.save(uid,'twitch',{}, {},expected=snapshot['_version'])

def test_refresh_preserves_identity_and_disconnect_removes_tokens(setup):
    store,uid,raw,session=setup
    service=OAuthService(store,'https://clipbot.example',transport=httpx.MockTransport(twitch_transport))
    service.vault.save(uid,'twitch',{'access_token':'old','refresh_token':'refresh','expires_at':0},{'id':'42','name':'Streamer'})
    assert service.refresh(uid,'twitch')['id']=='42'
    assert service.status(uid,'twitch')['connected']
    assert service.disconnect(uid,'twitch') is False  # Mock revocation returns 400, local removal still succeeds.
    assert service.vault.load(uid,'twitch') is None

def test_meta_destination_selection_isolated_and_tokens_private(setup):
    store,uid,raw,session=setup
    service=OAuthService(store,'https://clipbot.example')
    tokens={'access_token':'META-SECRET','expires_at':time.time()+300,'destinations':[{'id':'page1','name':'Page One','access_token':'PAGE-SECRET'}]}
    service.vault.save(uid,'facebook',tokens,{'id':'owner','name':'Owner','destinationSelected':False})
    assert service.destinations(uid,'facebook')==[{'id':'page1','name':'Page One'}]
    assert service.destinations('different-user','facebook')==[]
    with pytest.raises(OAuthInvalid):service.select(uid,'facebook','not-authorized')
    service.select(uid,'facebook','page1')
    assert service.status(uid,'facebook')['accountName']=='Page One'
    assert not service.status(uid,'facebook')['destinationRequired']

def test_declined_callback_consumes_state_and_never_connects(setup):
    store,uid,raw,session=setup;service=OAuthService(store,'https://clipbot.example')
    url,cookie=service.start(session,'twitch');state=parse_qs(urlsplit(url).query)['state'][0]
    with pytest.raises(OAuthUnavailable):service.callback('twitch',state,cookie,'','access_denied')
    with pytest.raises(OAuthInvalid):service.callback('twitch',state,cookie,'code')
    assert service.vault.load(uid,'twitch') is None


@pytest.mark.parametrize('platform', ['kick','tiktok','instagram','facebook'])
def test_each_provider_exchange_and_identity(setup,platform):
    store,uid,raw,session=setup
    def handler(request):
        path=request.url.path
        if path in ('/oauth/token','/v2/oauth/token/','/v24.0/oauth/access_token'):
            return httpx.Response(200,json={'access_token':'SECRET','refresh_token':'REFRESH','scope':'user.info.basic,video.publish',**({} if path=='/v24.0/oauth/access_token' else {'expires_in':3600})})
        if path=='/oauth/token/introspect':return httpx.Response(200,json={'data':{'active':True,'client_id':'public-app-id','token_type':'user','scope':'user:read channel:read'}})
        if path=='/public/v1/users':return httpx.Response(200,json={'data':[{'user_id':42,'name':'Kick User'}]})
        if path=='/v2/user/info/':return httpx.Response(200,json={'data':{'user':{'open_id':'42','display_name':'TikTok User'}},'error':{'code':'ok'}})
        if path=='/v24.0/debug_token':return httpx.Response(200,json={'data':{'is_valid':True,'app_id':'public-app-id','type':'USER','user_id':'42','expires_at':int(time.time())+3600}})
        if path=='/v24.0/me':return httpx.Response(200,json={'id':'42','name':'Meta User'})
        if path=='/v24.0/me/permissions':return httpx.Response(200,json={'data':[{'permission':scope,'status':'granted'} for scope in ['pages_show_list','pages_read_engagement','pages_manage_posts','instagram_basic','instagram_content_publish']]})
        if path=='/v24.0/me/accounts':return httpx.Response(200,json={'data':[{'id':'p1','name':'Page','tasks':['CREATE_CONTENT'],'access_token':'PAGE-SECRET','instagram_business_account':{'id':'i1','username':'Instagram User'}}]})
        return httpx.Response(404,json={})
    service=OAuthService(store,'https://clipbot.example',transport=httpx.MockTransport(handler))
    url,cookie=service.start(session,platform);state=parse_qs(urlsplit(url).query)['state'][0]
    callback_uid,profile=service.callback(platform,state,cookie,'code')
    assert callback_uid==uid and profile['id']=='42'
    assert service.status(uid,platform)['connected']
    assert 'SECRET' not in json.dumps(service.status(uid,platform))
    if platform in ('instagram','facebook'):assert profile['destinationSelected']

@pytest.mark.parametrize('bad', [None,{},'oops',[None]])
def test_malformed_identity_does_not_leak_or_save(setup,bad):
    store,uid,raw,session=setup
    def handler(request):
        if request.url.path=='/helix/users':return httpx.Response(200,json={'data':bad})
        return twitch_transport(request)
    service=OAuthService(store,'https://clipbot.example',transport=httpx.MockTransport(handler))
    url,cookie=service.start(session,'twitch');state=parse_qs(urlsplit(url).query)['state'][0]
    with pytest.raises(OAuthUnavailable):service.callback('twitch',state,cookie,'code')
    assert service.vault.load(uid,'twitch') is None


def test_refresh_lease_blocks_duplicate_dispatch(setup):
    store,uid,raw,session=setup;calls=[]
    service=OAuthService(store,'https://clipbot.example',transport=httpx.MockTransport(lambda request:calls.append(request)))
    lease=service.vault.claim(uid,'twitch')
    with pytest.raises(OAuthInvalid):service.refresh(uid,'twitch')
    assert not calls
    service.vault.release(uid,'twitch',lease)
    second=service.vault.claim(uid,'twitch')
    service.vault.release(uid,'twitch',second)

@pytest.mark.parametrize('platform,response', [('twitch',''),('kick','OK')])
def test_revocation_accepts_official_empty_or_plain_text_success(setup,platform,response):
    store,uid,raw,session=setup
    def handler(request):
        if platform=='kick':assert request.headers['content-type']=='application/x-www-form-urlencoded'
        return httpx.Response(200,text=response)
    service=OAuthService(store,'https://clipbot.example',transport=httpx.MockTransport(handler))
    service.vault.save(uid,platform,{'access_token':'SECRET','expires_at':time.time()+100},{'id':'42','name':'One'})
    assert service.disconnect(uid,platform)
    assert service.vault.load(uid,platform) is None


def test_concurrent_refresh_dispatch_and_disconnect_while_provider_waits(setup):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event
    store,uid,raw,session=setup;started=Event();release=Event();calls=[]
    def handler(request):
        if request.url.path=='/oauth2/token':
            calls.append(request)
            started.set()
            assert release.wait(5)
        return twitch_transport(request)
    service=OAuthService(store,'https://clipbot.example',transport=httpx.MockTransport(handler))
    service.vault.save(uid,'twitch',{'access_token':'old','refresh_token':'old-refresh','expires_at':0},{'id':'42','name':'Streamer'})
    with ThreadPoolExecutor(max_workers=1) as executor:
        pending=executor.submit(service.refresh,uid,'twitch')
        try:
            assert started.wait(3)
            with pytest.raises(OAuthInvalid):service.refresh(uid,'twitch')
            assert len(calls)==1
            service.disconnect(uid,'twitch')
        finally:release.set()
        with pytest.raises(OAuthInvalid):pending.result(timeout=5)
    assert service.vault.load(uid,'twitch') is None


def test_failed_callback_reports_safe_diagnostic_without_provider_secrets(setup,caplog):
    store,uid,raw,session=setup
    service=OAuthService(store,'https://clipbot.example',transport=httpx.MockTransport(lambda request:httpx.Response(401,json={'error':'SECRET-PROVIDER-BODY'})))
    with TestClient(create_app(store,origin='https://clipbot.example',oauth=service),base_url='https://clipbot.example') as client:
        client.cookies.set('clipbot_session',raw)
        response=client.post('/api/connections/twitch/start',json={'accountType':'personal'},headers={'Origin':'https://clipbot.example','X-CSRF-Token':session['csrf']})
        state=parse_qs(urlsplit(response.json()['authorizationUrl']).query)['state'][0]
        with caplog.at_level('WARNING'):
            result=client.get('/api/connections/twitch/callback',params={'code':'SECRET-AUTH-CODE','state':state},follow_redirects=False)
        assert 'result=failed' in result.headers['location']
        assert 'http_status=401' in caplog.text
        assert 'reason=The platform could not authorize' in caplog.text
        assert 'SECRET' not in caplog.text and state not in caplog.text


def test_meta_exchange_without_duration_uses_verified_expiry(setup):
    store,uid,raw,session=setup
    expiry=int(time.time())+3600
    def handler(request):
        assert request.url.path=='/v24.0/debug_token'
        assert request.headers['authorization']=='Bearer public-app-id|private-app-secret'
        return httpx.Response(200,json={'data':{'is_valid':True,'app_id':'public-app-id','type':'USER','user_id':'42','expires_at':expiry,'data_access_expires_at':expiry-100}})
    service=OAuthService(store,'https://clipbot.example',transport=httpx.MockTransport(handler))
    tokens=service.meta_tokens({'access_token':'SECRET'},'public-app-id','private-app-secret')
    assert tokens['expires_at']<=expiry-99 and tokens['verified_user_id']=='42'

@pytest.mark.parametrize('info', [
 {'is_valid':False,'app_id':'public-app-id','type':'USER','user_id':'42','expires_at':9999999999},
 {'is_valid':True,'app_id':'wrong','type':'USER','user_id':'42','expires_at':9999999999},
 {'is_valid':True,'app_id':'public-app-id','type':'USER','user_id':'42','expires_at':1},
 {'is_valid':True,'app_id':'public-app-id','type':'USER','user_id':'42'}])
def test_meta_expiry_verification_fails_closed(setup,info):
    store,uid,raw,session=setup
    service=OAuthService(store,'https://clipbot.example',transport=httpx.MockTransport(lambda request:httpx.Response(200,json={'data':info})))
    with pytest.raises(OAuthUnavailable):service.meta_tokens({'access_token':'SECRET'},'public-app-id','private-app-secret')


def test_destination_diagnostics_distinguish_filtering_without_private_data(setup,caplog):
    store,uid,raw,session=setup
    def handler(request):
        if request.url.path.endswith('/me'):return httpx.Response(200,json={'id':'42','name':'PRIVATE-NAME'})
        if request.url.path.endswith('/permissions'):return httpx.Response(200,json={'data':[{'permission':s,'status':'granted'} for s in ['pages_show_list','pages_read_engagement','pages_manage_posts']]})
        return httpx.Response(200,json={'data':[{'id':'SECRET-ID','name':'PRIVATE-PAGE','access_token':'SECRET-TOKEN','tasks':['ANALYZE']}]})
    service=OAuthService(store,'https://clipbot.example',transport=httpx.MockTransport(handler))
    with caplog.at_level('WARNING'),pytest.raises(OAuthUnavailable):service.identity('facebook',{'access_token':'SECRET-ACCESS'},'public-app-id')
    assert 'returned=1' in caplog.text and 'missing_publish_task=1' in caplog.text
    assert 'SECRET' not in caplog.text and 'PRIVATE' not in caplog.text

def test_kick_grant_uses_verified_scopes_and_rejects_profile_only(setup):
 store,uid,raw,session=setup
 def transport(scope):
  def respond(request):
   if request.url.path.endswith('/introspect'):return httpx.Response(200,json={'data':{'active':True,'client_id':'public-app-id','token_type':'user','scope':scope}})
   if request.url.path.endswith('/users'):return httpx.Response(200,json={'data':[{'user_id':42,'name':'Kick user'}]})
   return httpx.Response(400,json={})
  return httpx.MockTransport(respond)
 tokens={'access_token':'PRIVATE','scopes':['user:read']}
 service=OAuthService(store,'https://clipbot.example',transport=transport('user:read'))
 with pytest.raises(OAuthUnavailable,match='channel access'):service.identity('kick',dict(tokens),'public-app-id')
 service=OAuthService(store,'https://clipbot.example',transport=transport('user:read channel:read'))
 assert service.identity('kick',tokens,'public-app-id')['id']=='42'
 assert tokens['scopes']==['user:read','channel:read']
 service.vault.save(uid,'kick',{'access_token':'PRIVATE','refresh_token':'PRIVATE','expires_at':time.time()+3600,'scopes':['user:read']},{'id':'42','name':'Kick user'})
 status=service.status(uid,'kick');assert status['connected'] and not status['monitoringReady'] and status['status']=='permissions_missing'
 assert 'PRIVATE' not in str(status)
 url,_=service.start(session,'kick');assert '%20' in url;assert parse_qs(urlsplit(url).query)['scope']==['user:read channel:read']

def test_incomplete_kick_reconnect_preserves_existing_connection(setup):
 store,uid,raw,session=setup
 def respond(request):
  if request.url.path=='/oauth/token':return httpx.Response(200,json={'access_token':'NEW-PRIVATE','refresh_token':'NEW-REFRESH','expires_in':3600,'scope':'user:read'})
  if request.url.path.endswith('/introspect'):return httpx.Response(200,json={'data':{'active':True,'client_id':'public-app-id','token_type':'user','scope':'user:read'}})
  return httpx.Response(400,json={})
 service=OAuthService(store,'https://clipbot.example',transport=httpx.MockTransport(respond))
 service.vault.save(uid,'kick',{'access_token':'OLD-PRIVATE','refresh_token':'OLD-REFRESH','expires_at':time.time()+3600,'scopes':['user:read','channel:read']},{'id':'42','name':'Existing'})
 url,cookie=service.start(session,'kick');state=parse_qs(urlsplit(url).query)['state'][0]
 with pytest.raises(OAuthUnavailable,match='channel access'):service.callback('kick',state,cookie,'new-code')
 assert service.vault.load(uid,'kick')['tokens']['access_token']=='OLD-PRIVATE'
