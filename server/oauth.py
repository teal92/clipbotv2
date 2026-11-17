"""Official OAuth endpoints only; provider errors never return secrets to customers."""
import base64,hashlib,hmac,os,re,secrets,time,logging
from urllib.parse import urlencode,urlsplit,quote
import httpx
from .oauth_store import OAuthVault,OAuthInvalid

class OAuthUnavailable(Exception):
    pass

CONFIG={
 'twitch':('TWITCH_CLIENT_ID','TWITCH_CLIENT_SECRET','https://id.twitch.tv/oauth2/authorize','https://id.twitch.tv/oauth2/token','chat:read'),
 'kick':('KICK_CLIENT_ID','KICK_CLIENT_SECRET','https://id.kick.com/oauth/authorize','https://id.kick.com/oauth/token','user:read channel:read'),
 'tiktok':('TIKTOK_CLIENT_KEY','TIKTOK_CLIENT_SECRET','https://www.tiktok.com/v2/auth/authorize/','https://open.tiktokapis.com/v2/oauth/token/','user.info.basic,video.publish'),
 'instagram':('META_APP_ID','META_APP_SECRET','https://www.facebook.com/{version}/dialog/oauth','https://graph.facebook.com/{version}/oauth/access_token','pages_show_list,pages_read_engagement,instagram_basic,instagram_content_publish'),
 'facebook':('META_APP_ID','META_APP_SECRET','https://www.facebook.com/{version}/dialog/oauth','https://graph.facebook.com/{version}/oauth/access_token','pages_show_list,pages_read_engagement,pages_manage_posts')
}

class OAuthService:
    def __init__(self,store,origin,transport=None):
        logging.getLogger('httpx').setLevel(logging.WARNING)
        logging.getLogger('httpcore').setLevel(logging.WARNING)
        self.store=store;self.origin=origin;self.transport=transport;self.vault=OAuthVault(store)
        self.version=os.getenv('META_GRAPH_VERSION','v24.0')
        if not re.fullmatch(r'v[0-9]{1,2}\.0',self.version):raise RuntimeError('Invalid Meta API version')
        parsed=urlsplit(origin)
        self.safe_origin=bool(parsed.scheme=='https' and parsed.hostname and not parsed.username and not parsed.password and not parsed.query and not parsed.fragment and parsed.path in ('','/'))
    def ready(self,platform):
        if platform not in CONFIG or not self.safe_origin or not self.vault.cipher:return False
        return all((value:=os.getenv(name,'')) and value==value.strip() and not any(ord(c)<32 for c in value) for name in CONFIG[platform][:2])
    def callback_url(self,platform):return f'{self.origin}/api/connections/{platform}/callback'
    def credentials(self,platform):
        if not self.ready(platform):raise OAuthUnavailable('This platform connection needs service setup. No account has been connected.')
        config=CONFIG[platform];return os.environ[config[0]],os.environ[config[1]]
    def start(self,session,platform):
        client,_=self.credentials(platform)
        verifier=secrets.token_urlsafe(64) if platform=='kick' else ''
        state,cookie=self.vault.begin(session,platform,verifier)
        params={'response_type':'code','redirect_uri':self.callback_url(platform),'state':state,'scope':CONFIG[platform][4]}
        # Read-only dashboard analytics remain optional; denying them does not break publishing.
        analytics_scope={'tiktok':'video.list','instagram':'instagram_manage_insights','facebook':'read_insights'}.get(platform)
        if analytics_scope:params['scope']+=','+analytics_scope
        # Request portfolio discovery consent without making it mandatory for directly managed Pages.
        if platform in ('facebook','instagram'):params['scope']+=',business_management'
        params['client_key' if platform=='tiktok' else 'client_id']=client
        if platform=='kick':
            params.update(code_challenge=base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip('='),code_challenge_method='S256')
        return CONFIG[platform][2].format(version=self.version)+'?'+urlencode(params,quote_via=quote),cookie
    def request(self,method,url,allow_empty=False,**kwargs):
        # No redirects or environment proxies: a provider cannot redirect credentials elsewhere.
        deadline=time.monotonic()+15
        try:
            with httpx.Client(timeout=12,follow_redirects=False,trust_env=False,transport=self.transport) as client:
                with client.stream(method,url,**kwargs) as response:
                    if response.status_code not in (200,201):
                        logging.getLogger('clipbot.oauth').warning('Platform request failed: endpoint=%s http_status=%s',urlsplit(url).path,response.status_code)
                        error=OAuthUnavailable('The platform could not authorize this account. Try again or check its app permissions.')
                        error.http_status=response.status_code
                        raise error
                    content=b''
                    for chunk in response.iter_bytes():
                        if time.monotonic()>deadline:raise OAuthUnavailable('The platform took too long to respond. Try again.')
                        content+=chunk
                        if len(content)>262144:raise OAuthUnavailable('The platform response was too large. Try again.')
                    if allow_empty:return {}
                    import json
                    data=json.loads(content)
                    if not isinstance(data,dict):raise ValueError()
                    return data
        except OAuthUnavailable:raise
        except (httpx.HTTPError,ValueError,TypeError):raise OAuthUnavailable('Could not reach the platform. Try again later.') from None
    def normalize(self,data,previous=None):
        access=data.get('access_token')
        if not isinstance(access,str) or not 1<=len(access)<=16000:raise OAuthUnavailable('The platform did not return valid authorization.')
        raw_duration=data.get('expires_in')
        if type(raw_duration) is not int and not (isinstance(raw_duration,str) and raw_duration.isdigit() and len(raw_duration)<12):raise OAuthUnavailable('The platform returned invalid authorization timing.')
        duration=int(raw_duration)
        if not 0<duration<=366*86400:raise OAuthUnavailable('The platform returned invalid authorization timing.')
        refresh=data.get('refresh_token',(previous or {}).get('refresh_token',''))
        if not isinstance(refresh,str) or len(refresh)>16000:raise OAuthUnavailable('The platform returned invalid authorization.')
        scope=data.get('scope',(previous or {}).get('scopes',[]))
        if isinstance(scope,str):scope=re.split(r'[, ]+',scope)
        if not isinstance(scope,list) or any(not isinstance(s,str) or len(s)>100 for s in scope):raise OAuthUnavailable('The platform returned invalid permissions.')
        return {'access_token':access,'refresh_token':refresh,'expires_at':time.time()+duration,'scopes':scope}
    def meta_tokens(self,data,client,secret):
        access=data.get('access_token')
        if not isinstance(access,str) or not 1<=len(access)<=16000:raise OAuthUnavailable('Meta did not return valid authorization.')
        info=self.request('GET',f'https://graph.facebook.com/{self.version}/debug_token',headers={'Authorization':'Bearer '+client+'|'+secret},params={'input_token':access}).get('data')
        if not isinstance(info,dict) or info.get('is_valid') is not True or str(info.get('app_id',''))!=client or info.get('type')!='USER' or not isinstance(info.get('user_id'),str) or not info['user_id']:raise OAuthUnavailable('Meta could not verify this account authorization.')
        now=time.time();deadlines=[]
        for field in ('expires_at','data_access_expires_at'):
            value=info.get(field)
            if value is None and field=='data_access_expires_at':continue
            if type(value) is not int or value<0:raise OAuthUnavailable('Meta did not provide verifiable authorization timing.')
            if value:
                if value<=now:raise OAuthUnavailable('Meta authorization has expired. Reconnect this account.')
                deadlines.append(value)
        # Explicit zero means no scheduled expiry. Still require fresh verification daily.
        expiry=min(deadlines) if deadlines else now+86400
        duration=max(1,int(min(expiry-now,366*86400)))
        normalized=self.normalize({**data,'expires_in':duration})
        normalized['verified_user_id']=info['user_id']
        normalized['meta_expiry_verified']=True
        return normalized
    def callback(self,platform,state,cookie,code,error='',current_uid=None):
        flow=self.vault.consume(platform,state,cookie)
        if current_uid and not hmac.compare_digest(current_uid,flow['user_id']):raise OAuthInvalid('Sign in to the account that started this connection.')
        if error:raise OAuthUnavailable('Authorization was declined or unavailable. No new account was connected.')
        if not isinstance(code,str) or not 1<=len(code)<=4096:raise OAuthInvalid('Start the connection again.')
        client,secret=self.credentials(platform)
        form={'client_key' if platform=='tiktok' else 'client_id':client,'client_secret':secret,'redirect_uri':self.callback_url(platform),'code':code,'grant_type':'authorization_code'}
        if platform=='kick':form['code_verifier']=flow['verifier']
        if platform in ('instagram','facebook'):
            data=self.request('GET',CONFIG[platform][3].format(version=self.version),params=form)
            short=data.get('access_token')
            if not isinstance(short,str) or not short:raise OAuthUnavailable('The platform did not return authorization.')
            data=self.request('GET',CONFIG[platform][3].format(version=self.version),params={'grant_type':'fb_exchange_token','client_id':client,'client_secret':secret,'fb_exchange_token':short})
        else:data=self.request('POST',CONFIG[platform][3],data=form)
        tokens=self.meta_tokens(data,client,secret) if platform in ('instagram','facebook') else self.normalize(data)
        profile=self.identity(platform,tokens,client)
        self.vault.save(flow['user_id'],platform,tokens,profile,flow)
        return flow['user_id'],profile
    @staticmethod
    def profile(identity,name,**extra):
        if not isinstance(identity,(str,int)) or not str(identity) or len(str(identity))>150:raise OAuthUnavailable('The platform did not identify this account.')
        if not isinstance(name,str) or not name or len(name)>200:raise OAuthUnavailable('The platform did not identify this account.')
        return {'id':str(identity),'name':name,**extra}
    @staticmethod
    def rows(data,key='data'):
        rows=data.get(key,[])
        if not isinstance(rows,list) or len(rows)>100 or any(not isinstance(row,dict) for row in rows):raise OAuthUnavailable('The platform returned invalid account information.')
        return rows
    def identity(self,platform,tokens,client):
        access=tokens['access_token'];headers={'Authorization':'Bearer '+access}
        if platform=='twitch':
            verified=self.request('GET','https://id.twitch.tv/oauth2/validate',headers={'Authorization':'OAuth '+access})
            if verified.get('client_id')!=client or not verified.get('user_id'):raise OAuthUnavailable('The platform authorization did not match ClipBot.')
            rows=self.rows(self.request('GET','https://api.twitch.tv/helix/users',headers={**headers,'Client-Id':client}))
            if len(rows)!=1 or str(rows[0].get('id'))!=str(verified['user_id']):raise OAuthUnavailable('The platform did not identify this account.')
            granted=verified.get('scopes',tokens['scopes'])
            if not isinstance(granted,list) or any(not isinstance(v,str) or len(v)>100 for v in granted):raise OAuthUnavailable('Twitch returned invalid permissions.')
            tokens['scopes']=granted
            return self.profile(rows[0].get('id'),rows[0].get('display_name'))
        if platform=='kick':
            check=self.request('POST','https://id.kick.com/oauth/token/introspect',headers=headers).get('data',{})
            if not isinstance(check,dict):raise OAuthUnavailable('The platform returned invalid authorization.')
            if check.get('active') is not True or check.get('client_id')!=client or check.get('token_type')!='user':raise OAuthUnavailable('The platform authorization did not match ClipBot.')
            granted=check.get('scope')
            if not isinstance(granted,str) or len(granted)>2000:raise OAuthUnavailable('Kick did not return verifiable channel permissions. Start the connection again.')
            tokens['scopes']=granted.split()
            if not {'user:read','channel:read'}<=set(tokens['scopes']):raise OAuthUnavailable('Kick did not grant channel access. Approve permission to view channel information when reconnecting ClipBot.')
            rows=self.rows(self.request('GET','https://api.kick.com/public/v1/users',headers=headers))
            if len(rows)!=1:raise OAuthUnavailable('The platform did not identify this account.')
            return self.profile(rows[0].get('user_id'),rows[0].get('name'))
        if platform=='tiktok':
            data=self.request('GET','https://open.tiktokapis.com/v2/user/info/',headers=headers,params={'fields':'open_id,display_name'})
            if not isinstance(data.get('error',{}),dict) or not isinstance(data.get('data',{}),dict):raise OAuthUnavailable('TikTok returned invalid account information.')
            if data.get('error',{}).get('code') not in ('ok',None):raise OAuthUnavailable('TikTok could not identify this account.')
            user=data.get('data',{}).get('user',{})
            if not isinstance(user,dict):raise OAuthUnavailable('TikTok returned invalid account information.')
            return self.profile(user.get('open_id'),user.get('display_name'),publishingPermission='video.publish' in tokens['scopes'])
        root=f'https://graph.facebook.com/{self.version}'
        proof=hmac.new(os.environ['META_APP_SECRET'].encode(),access.encode(),hashlib.sha256).hexdigest()
        params={'appsecret_proof':proof}
        user=self.request('GET',root+'/me',headers=headers,params={**params,'fields':'id,name'})
        if tokens.get('verified_user_id') and str(user.get('id',''))!=tokens['verified_user_id']:raise OAuthUnavailable('Meta account identity did not match its authorization.')
        permissions=self.rows(self.request('GET',root+'/me/permissions',headers=headers,params=params))
        granted={row.get('permission') for row in permissions if row.get('status')=='granted'}
        required=set(CONFIG[platform][4].split(','))
        if not required.issubset(granted):raise OAuthUnavailable('Approve the required Page and publishing permissions to connect this account.')
        tokens['scopes']=sorted(granted)
        fields='id,name,access_token,tasks'+(',instagram_business_account{id,username,name}' if platform=='instagram' else '')
        pages=self.request('GET',root+'/me/accounts',headers=headers,params={**params,'fields':fields,'limit':100})
        # Do not follow provider-supplied paging URLs containing credentials.
        destinations=[]
        page_rows=self.rows(pages)
        missing_task=missing_token=missing_instagram=0
        for page in page_rows:
            tasks=page.get('tasks',[])
            if not isinstance(tasks,list) or any(not isinstance(task,str) for task in tasks):raise OAuthUnavailable('Meta returned invalid Page permissions.')
            if not set(tasks).intersection({'CREATE_CONTENT','MANAGE','PROFILE_PLUS_CREATE_CONTENT','PROFILE_PLUS_FULL_CONTROL'}):
                missing_task+=1;continue
            token=page.get('access_token')
            if not isinstance(token,str) or not token:
                missing_token+=1;continue
            target=page.get('instagram_business_account') if platform=='instagram' else page
            if not target:
                missing_instagram+=1;continue
            if not isinstance(target,dict):raise OAuthUnavailable('Meta returned invalid destination information.')
            dest=self.profile(target.get('id'),target.get('username') or target.get('name'));dest['page_id']=str(page.get('id'));dest['access_token']=token
            destinations.append(dest)
        if not destinations:
            logging.getLogger('clipbot.oauth').warning('Meta destination discovery: platform=%s returned=%d missing_publish_task=%d missing_page_token=%d missing_linked_instagram=%d',platform,len(page_rows),missing_task,missing_token,missing_instagram)
            if not page_rows:raise OAuthUnavailable('Meta returned no authorized Pages. Check the Pages selected for this app and your Page access.')
            if missing_task==len(page_rows):raise OAuthUnavailable('Meta returned Pages without a publishing task. Check your content publishing access to the selected Page.')
            if platform=='instagram' and missing_instagram:raise OAuthUnavailable('Meta returned a Page without a linked professional Instagram account. Check the Page Instagram link.')
            raise OAuthUnavailable('Meta did not provide an eligible Page publishing token. Check the app Page permissions.')
        tokens['destinations']=destinations
        profile=self.profile(user.get('id'),user.get('name'),destinationSelected=False)
        if len(destinations)==1:profile.update(destinationSelected=True,destinationId=destinations[0]['id'],destinationName=destinations[0]['name'])
        return profile
    def destinations(self,uid,platform):
        data=self.vault.load(uid,platform)
        if not data:return []
        return [{'id':row['id'],'name':row['name']} for row in data['tokens'].get('destinations',[])]
    def select(self,uid,platform,destination):
        lease=self.vault.claim(uid,platform)
        try:
            data=self.vault.load(uid,platform)
            if not data:raise OAuthInvalid('Connect your account first.')
            match=next((row for row in data['tokens'].get('destinations',[]) if row['id']==destination),None)
            if not match:raise OAuthInvalid('Choose a destination authorized by your account.')
            data['profile'].update(destinationSelected=True,destinationId=match['id'],destinationName=match['name'])
            self.vault.save(uid,platform,data['tokens'],data['profile'],expected=data['_version'])
        finally:self.vault.release(uid,platform,lease)
    def refresh(self,uid,platform):
        lease=self.vault.claim(uid,platform)
        try:
            data=self.vault.load(uid,platform)
            if not data:raise OAuthInvalid('Connect your account first.')
            tokens=data['tokens'];client,secret=self.credentials(platform)
            if platform in ('instagram','facebook'):raise OAuthUnavailable('Reconnect this Meta account when its authorization expires.')
            if not tokens.get('refresh_token'):raise OAuthUnavailable('Reconnect this account to renew authorization.')
            form={'grant_type':'refresh_token','refresh_token':tokens['refresh_token'],'client_secret':secret,'client_key' if platform=='tiktok' else 'client_id':client}
            result=self.normalize(self.request('POST',CONFIG[platform][3],data=form),tokens)
            profile=self.identity(platform,result,client)
            if profile['id']!=data['profile']['id']:raise OAuthUnavailable('The refreshed account did not match. Reconnect it.')
            self.vault.save(uid,platform,result,profile,expected=data['_version'])
            return profile
        finally:self.vault.release(uid,platform,lease)
    def disconnect(self,uid,platform):
        data=self.vault.load(uid,platform)
        # Remove local access first even if the provider is offline.
        self.vault.disconnect(uid,platform)
        if not data:return True
        token=data['tokens']['access_token']
        try:
            client,_=self.credentials(platform)
            if platform=='twitch':self.request('POST','https://id.twitch.tv/oauth2/revoke',allow_empty=True,data={'client_id':client,'token':token})
            elif platform=='kick':self.request('POST','https://id.kick.com/oauth/revoke',allow_empty=True,headers={'Content-Type':'application/x-www-form-urlencoded'},params={'token':token,'token_hint_type':'access_token'})
            elif platform=='tiktok':
                _,secret=self.credentials(platform)
                result=self.request('POST','https://open.tiktokapis.com/v2/oauth/revoke/',data={'client_key':client,'client_secret':secret,'token':token})
                if result.get('error'):return False
            else:
                # Meta authorization can be shared by both destinations. Keep sibling access intact.
                sibling='instagram' if platform=='facebook' else 'facebook'
                other=self.vault.load(uid,sibling)
                if other and other['profile']['id']==data['profile']['id']:return False
                self.request('DELETE',f'https://graph.facebook.com/{self.version}/me/permissions',headers={'Authorization':'Bearer '+token})
            return True
        except (OAuthUnavailable,OAuthInvalid):return False
    def status(self,uid,platform):
        result={'connected':False,'authorizationAvailable':self.ready(platform),'publishingReady':False,'status':'setup_required'}
        try:data=self.vault.load(uid,platform)
        except OAuthInvalid:result['status']='reconnect_required';return result
        if not data:return result if not result['authorizationAvailable'] else {**result,'status':'not_connected'}
        expired=data['tokens']['expires_at']<=time.time()
        result.update(connected=not expired,accountName=data['profile'].get('destinationName') or data['profile']['name'],status='reconnect_required' if expired else 'connected',destinationRequired=platform in ('instagram','facebook') and not data['profile'].get('destinationSelected',False))
        if platform=='kick' and not expired and 'channel:read' not in data['tokens'].get('scopes',[]):result.update(status='permissions_missing',monitoringReady=False,message='Kick sign-in is linked, but channel access is missing. Reconnect and approve viewing channel information.')
        elif platform=='kick':result['monitoringReady']=not expired
        # Publishing execution/worker is a separate gate, never implied by authorization.
        return result
