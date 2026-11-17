"""Official Twitch/Kick discovery using the requesting account's stored OAuth."""
import re,time
from urllib.parse import urlsplit
from .oauth import OAuthUnavailable
from .scouts import source_identity,ScoutDenied

def thumbnail_url(platform,value):
    if not isinstance(value,str) or len(value)>2000:return None
    value=value.replace('{width}','320').replace('{height}','180')
    try:
        parsed=urlsplit(value)
        allowed={'twitch':{'static-cdn.jtvnw.net'},'kick':{'images.kick.com'}}
        if parsed.scheme!='https' or parsed.hostname not in allowed.get(platform,set()) or parsed.username or parsed.password or parsed.port not in (None,443) or parsed.fragment:return None
        return value
    except ValueError:return None

class Directory:
    def __init__(self,oauth):
        from threading import Lock
        from collections import OrderedDict
        self.oauth=oauth;self.coverage_lock=Lock();self.coverage_cache=OrderedDict()
    def category_coverage(self,uid,platform,categories):
        """Read-only top-three results, bounded to ten categories and four requests."""
        if not isinstance(categories,list) or len(categories)>10 or any(not isinstance(cid,str) or not re.fullmatch(r'[0-9]{1,20}',cid) for cid in categories):raise ScoutDenied('Choose up to ten valid categories.')
        # Check current authorization even when returning cached account-scoped data.
        self.access(uid,platform)
        key=(uid,platform,tuple(dict.fromkeys(categories)))
        from concurrent.futures import ThreadPoolExecutor
        from copy import deepcopy
        with self.coverage_lock:
            cached=self.coverage_cache.get(key)
            if cached and cached[0]>time.monotonic():return deepcopy(cached[1])
            def ranked(cid):
                try:
                    rows=self.streams(uid,platform,[],[cid])
                    rows=sorted((r for r in rows if r.get('live') is True and r.get('categoryId')==cid),key=lambda r:-r['viewers'])[:3]
                    return cid,rows,None
                except OAuthUnavailable:return cid,[],'Live category data unavailable. Check Connect Accounts.'
            with ThreadPoolExecutor(max_workers=4) as pool:groups=list(pool.map(ranked,key[2]))
            result={'sources':[r for cid,rows,error in groups for r in rows],'errors':{cid:error for cid,rows,error in groups if error}}
            self.coverage_cache[key]=(time.monotonic()+60,result)
            while len(self.coverage_cache)>128:self.coverage_cache.popitem(last=False)
            return deepcopy(result)
    def access(self,uid,platform):
        if platform not in ('twitch','kick'):raise ScoutDenied('Choose Twitch or Kick.')
        record=self.oauth.vault.load(uid,platform)
        if not record:raise OAuthUnavailable('Connect this streaming account first.')
        if record['tokens']['expires_at']<=time.time()+60:
            self.oauth.refresh(uid,platform);record=self.oauth.vault.load(uid,platform)
            if not record:raise OAuthUnavailable('Reconnect this streaming account.')
        headers={'Authorization':'Bearer '+record['tokens']['access_token']}
        if platform=='twitch':headers['Client-Id']=self.oauth.credentials(platform)[0]
        return headers
    @staticmethod
    def normalized(platform,row,explicit=False):
        if platform=='twitch':
            login=row.get('user_login');category={'id':row.get('game_id'),'name':row.get('game_name')};live=row.get('type','live')=='live';sid=row.get('id');viewers=row.get('viewer_count',0)
        else:
            channel=row.get('channel') or {};stream=row.get('stream') or {}
            if not isinstance(channel,dict) or not isinstance(stream,dict):raise OAuthUnavailable('The platform returned invalid channel information.')
            login=row.get('slug') or channel.get('slug');category=row.get('category') or {};live=stream.get('is_live') is True if explicit else True;sid=row.get('id') or row.get('broadcaster_user_id');viewers=stream.get('viewer_count',row.get('viewer_count',0)) if explicit else row.get('viewer_count',0)
        identity=source_identity({'platform':platform,'login':login})
        if not isinstance(category,dict) or not isinstance(category.get('name',''),str):raise OAuthUnavailable('The platform returned invalid category information.')
        cid=str(category.get('id') or '')
        if cid and not re.fullmatch(r'[A-Za-z0-9_-]{1,100}',cid):raise OAuthUnavailable('The platform returned invalid category information.')
        if type(viewers) is not int or viewers<0:raise OAuthUnavailable('The platform returned invalid live information.')
        return {**identity,'live':live,'streamId':str(sid or '')[:100],'categoryId':cid,'categoryName':category.get('name','')[:100],'viewers':viewers,'thumbnailUrl':thumbnail_url(platform,row.get('thumbnail_url') if platform=='twitch' else row.get('thumbnail') or stream.get('thumbnail'))}
    def streams(self,uid,platform,logins,categories):
        if not isinstance(logins,list) or len(logins)>65 or not isinstance(categories,list) or len(categories)>25:raise ScoutDenied('Too many discovery filters.')
        for login in logins:source_identity({'platform':platform,'login':login})
        if any(not isinstance(c,str) or not c.isdigit() or len(c)>20 for c in categories):raise ScoutDenied('Choose a valid platform category.')
        headers=self.access(uid,platform)
        if platform=='twitch':
            params=[('first','100')]+([('user_login',login) for login in logins] if logins else [('game_id',c) for c in categories])
            data=self.oauth.request('GET','https://api.twitch.tv/helix/streams',headers=headers,params=params)
            return [self.normalized(platform,row) for row in self.oauth.rows(data)]
        if logins:
            data=self.oauth.request('GET','https://api.kick.com/public/v1/channels',headers=headers,params=[('slug',login) for login in logins])
            return [self.normalized(platform,row,True) for row in self.oauth.rows(data)]
        # The official v2 endpoint sorts by stream start time. v1 still provides viewer ranking.
        # One category filter per request, bounded by the validated 25-category batch.
        from concurrent.futures import ThreadPoolExecutor
        def ranked(category):
            params={'limit':100,'sort':'viewer_count'}
            if category:params['category_id']=category
            data=self.oauth.request('GET','https://api.kick.com/public/v1/livestreams',headers=headers,params=params)
            return [self.normalized(platform,row) for row in self.oauth.rows(data)]
        if not categories:return ranked(None)
        with ThreadPoolExecutor(max_workers=4) as pool:groups=list(pool.map(ranked,categories))
        top=[group[0] for group in groups if group]
        combined=sorted((row for group in groups for row in group),key=lambda row:-row['viewers'])
        unique={}
        for row in top+combined[:100]:unique.setdefault(row['login'],row)
        return list(unique.values())
    def lookup(self,uid,platform,login):
        identity=source_identity({'platform':platform,'login':login})
        if platform=='kick':return self.streams(uid,platform,[identity['login']],[])
        headers=self.access(uid,platform)
        users=self.oauth.rows(self.oauth.request('GET','https://api.twitch.tv/helix/users',headers=headers,params={'login':identity['login']}))
        if not users:return []
        live=self.streams(uid,platform,[identity['login']],[])
        if live:return live
        user=users[0]
        if user.get('login')!=identity['login']:raise OAuthUnavailable('The platform returned a mismatched channel.')
        return [{**identity,'live':False,'streamId':'','categoryId':'','categoryName':'','viewers':0}]
    def categories(self,uid,platform,query):
        if not isinstance(query,str) or not 3<=len(query.strip())<=100 or any(ord(c)<32 for c in query):raise ScoutDenied('Enter at least three characters to find a category.')
        headers=self.access(uid,platform)
        url='https://api.twitch.tv/helix/search/categories' if platform=='twitch' else 'https://api.kick.com/public/v2/categories'
        params={'query':query,'first':25} if platform=='twitch' else {'name':query,'limit':25}
        rows=self.oauth.rows(self.oauth.request('GET',url,headers=headers,params=params));result=[]
        for row in rows:
            cid=str(row.get('id',''));name=row.get('name')
            if not cid.isdigit() or not isinstance(name,str) or not 1<=len(name)<=100:raise OAuthUnavailable('The platform returned invalid categories.')
            result.append({'platform':platform,'id':cid,'name':name})
        return result

    def top_categories(self,uid,platform):
        if platform=='twitch':
            headers=self.access(uid,platform)
            rows=self.oauth.rows(self.oauth.request('GET','https://api.twitch.tv/helix/games/top',headers=headers,params={'first':25}))
            return [{'platform':platform,'id':str(r['id']),'name':r['name']} for r in rows if str(r.get('id','')).isdigit() and isinstance(r.get('name'),str) and 1<=len(r['name'])<=100]
        totals={}
        for stream in self.streams(uid,platform,[],[]):
            key=stream['categoryId']
            if not key:continue
            entry=totals.setdefault(key,{'platform':platform,'id':key,'name':stream['categoryName'],'viewers':0,'rankingBasis':'listed_live_streams'})
            entry['viewers']+=stream['viewers']
        return sorted(totals.values(),key=lambda v:-v['viewers'])[:25]
