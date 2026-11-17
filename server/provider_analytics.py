"""Read-only, bounded official provider analytics; no provider secrets in snapshots.

Each explicit refresh scans one page (20 public TikTok videos or 12 Meta videos).
Large accounts finish over subsequent refreshes. Partial scans never become totals.
Paging URLs are never followed, and expired/revoked authorizations hide cached views.
"""
import hashlib, json, re, secrets, time
from concurrent.futures import ThreadPoolExecutor

SCOPES = {'tiktok': 'video.list', 'instagram': 'instagram_manage_insights', 'facebook': 'read_insights'}

def count(value):
    return value if type(value) is int and 0 <= value <= 10**15 else None

def media_id(value):
    value = str(value)
    if not re.fullmatch(r'[0-9]{1,100}', value): raise ValueError('Invalid provider media identifier')
    return value

def metric(data, name):
    rows = data.get('data')
    if not isinstance(rows, list): return None
    for row in rows:
        if not isinstance(row, dict) or row.get('name') != name: continue
        total = row.get('total_value', {}).get('value')
        if count(total) is not None: return total
        values = row.get('values')
        if isinstance(values, list) and len(values) == 1 and isinstance(values[0], dict):
            return count(values[0].get('value'))
    return None

class ProviderAnalytics:
    def __init__(self, store, oauth):
        self.store = store; self.oauth = oauth
        with store.connection() as db:
            db.execute('CREATE TABLE IF NOT EXISTS dashboard_view_cache(user_id TEXT NOT NULL,account_key TEXT NOT NULL,data TEXT NOT NULL,updated REAL NOT NULL,lease TEXT NOT NULL DEFAULT \'\',lease_expires REAL NOT NULL DEFAULT 0,PRIMARY KEY(user_id,account_key))')

    def accounts(self, uid):
        accounts = []
        for platform in SCOPES:
            try: record = self.oauth.vault.load(uid, platform)
            except Exception: continue
            if not record: continue
            tokens = record['tokens']; profile = record['profile']
            destinations = [profile] if platform == 'tiktok' else tokens.get('destinations', [])
            for destination in destinations[:100]:
                identity = str(destination.get('id', ''))
                if not identity: continue
                key = hashlib.sha256((platform+'\0'+identity).encode()).hexdigest()[:32]
                status = 'not_collected'
                if tokens.get('expires_at', 0) <= time.time()+60: status = 'reconnect_required'
                elif SCOPES[platform] not in tokens.get('scopes', []): status = 'permission_required'
                accounts.append({'accountKey': key, 'platform': platform, 'name': str(destination.get('name') or identity)[:100], 'identity': identity, 'status': status, 'token': tokens.get('access_token') if platform == 'tiktok' else destination.get('access_token'), 'version': hashlib.sha256(record['_version'].encode()).hexdigest()})
        return accounts

    def cached(self, uid, key):
        with self.store.connection() as db: row = db.execute('SELECT * FROM dashboard_view_cache WHERE user_id=? AND account_key=?', (uid, key)).fetchone()
        return dict(row) if row else None

    def public(self, account, row=None):
        result = {k: account[k] for k in ('accountKey', 'platform', 'name', 'status')}
        result.update(views=None, observedViews=None, videoCount=0, fetchedAt=None, stale=False)
        if account['status'] != 'not_collected' or not row: return result
        data = json.loads(row['data'])
        if data.get('version') != account['version']: return result
        known = data.get('samples', {})
        values = [entry['views'] for entry in known.values() if count(entry.get('views')) is not None]
        result.update(status=data.get('status', 'unavailable'), views=sum(values) if values else (0 if data.get('status')=='available' else None), observedViews=sum(values) if values else None, videoCount=len(values), fetchedAt=data.get('fetchedAt'), stale=time.time()-data.get('fetchedAt',0)>900)
        if result['status'] in ('unavailable','refreshing'): result['views']=None
        return result

    def snapshot(self, uid):
        accounts = [self.public(a, self.cached(uid, a['accountKey'])) for a in self.accounts(uid)]
        complete = bool(accounts) and all(a['status']=='available' and not a['stale'] for a in accounts)
        known = [a['views'] for a in accounts if a['views'] is not None]
        return {'accounts': accounts, 'totalViews': sum(known) if complete else None, 'observedViews': sum(known) if known else None, 'complete': complete, 'meaning': 'Provider lifetime video views. TikTok includes public videos; Meta includes videos returned by the authorized account. Platforms define views differently; this is not unique viewers. Partial scans and missing permissions prevent a complete total.'}

    def refresh(self, uid, key):
        account = next((a for a in self.accounts(uid) if a['accountKey']==key), None)
        if not account: raise ValueError('Account unavailable')
        if account['status'] != 'not_collected': return self.public(account)
        now = time.time(); owner = secrets.token_hex(16)
        # Persisted lease and cooldown survive concurrent requests and server restarts.
        with self.store.connection(atomic=True) as db:
            row = db.execute('SELECT * FROM dashboard_view_cache WHERE user_id=? AND account_key=?', (uid,key)).fetchone()
            previous = json.loads(row['data']) if row else {}
            same = previous.get('version') == account['version']
            cooldown = 60 if previous.get('status')=='partial' else 900
            if row and (row['lease_expires']>now or same and now-row['updated']<cooldown): return self.public(account,dict(row))
            if not same: previous = {}
            db.execute('INSERT INTO dashboard_view_cache VALUES(?,?,?,?,?,?) ON CONFLICT(user_id,account_key) DO UPDATE SET lease=excluded.lease,lease_expires=excluded.lease_expires', (uid,key,json.dumps(previous),now,owner,now+90))
        try:
            samples, cursor, more, missing = self.collect(account, previous.get('cursor'))
            accumulated = previous.get('samples', {}) if previous.get('cursor') is not None else {}
            accumulated.update(samples)
            # Bound stored state as well as network work. A large account remains partial.
            capacity = len(accumulated)>10000
            if capacity: accumulated = dict(list(accumulated.items())[:10000])
            missing = missing or previous.get('missing',False) if previous.get('cursor') is not None else missing
            status = 'partial' if more or missing or capacity else 'available'
            if not accumulated and missing: status = 'unavailable'
            data = {'version': account['version'], 'status': status, 'samples': accumulated, 'cursor': cursor if more and not capacity else None, 'missing': missing, 'fetchedAt': time.time()}
        except Exception:
            # Keep old observations without presenting them as a successful refresh.
            data = {**previous, 'version': account['version'], 'status': 'unavailable'}
        # A disconnect or reconnect during I/O must not expose data under new consent.
        current = next((a for a in self.accounts(uid) if a['accountKey']==key), None)
        if not current or current['version'] != account['version']:
            with self.store.connection() as db: db.execute('DELETE FROM dashboard_view_cache WHERE user_id=? AND account_key=? AND lease=?',(uid,key,owner))
            return self.public(current or {**account,'status':'reconnect_required'})
        with self.store.connection() as db:
            db.execute("UPDATE dashboard_view_cache SET data=?,updated=?,lease='',lease_expires=0 WHERE user_id=? AND account_key=? AND lease=?", (json.dumps(data),time.time(),uid,key,owner))
        return self.public(current, self.cached(uid,key))

    def collect(self, account, cursor):
        token=account['token']; headers={'Authorization':'Bearer '+token}; platform=account['platform']; samples={}; missing=False
        if platform=='tiktok':
            body={'max_count':20}
            if type(cursor) is int and 0<=cursor<=2**63-1: body['cursor']=cursor
            response=self.oauth.request('POST','https://open.tiktokapis.com/v2/video/list/',headers={**headers,'Content-Type':'application/json'},params={'fields':'id'},json=body)
            if response.get('error',{}).get('code')!='ok': raise ValueError('Provider unavailable')
            data=response.get('data',{}); rows=data.get('videos')
            if not isinstance(rows,list) or len(rows)>20 or type(data.get('has_more')) is not bool: raise ValueError('Invalid provider response')
            ids=[media_id(r.get('id')) for r in rows]; more=data['has_more']; next_cursor=data.get('cursor')
            if more and (type(next_cursor) is not int or not 0<=next_cursor<=2**63-1 or next_cursor==cursor): raise ValueError('Invalid cursor')
            if ids:
                response=self.oauth.request('POST','https://open.tiktokapis.com/v2/video/query/',headers={**headers,'Content-Type':'application/json'},params={'fields':'id,view_count'},json={'filters':{'video_ids':ids}})
                if response.get('error',{}).get('code')!='ok': raise ValueError('Provider unavailable')
                returned=response.get('data',{}).get('videos')
                if not isinstance(returned,list) or len(returned)>20: raise ValueError('Invalid metrics')
                for row in returned:
                    identity=media_id(row.get('id')); views=count(row.get('view_count'))
                    if identity in ids and views is not None: samples[identity]={'views':views}
                missing=len(samples)!=len(set(ids))
            return samples,next_cursor,more,missing
        graph='https://graph.facebook.com/'+self.oauth.version
        identity=media_id(account['identity']); edge='media' if platform=='instagram' else 'videos'
        params={'fields':'id,media_type' if platform=='instagram' else 'id','limit':12}
        if isinstance(cursor,str) and 1<=len(cursor)<=2048: params['after']=cursor
        response=self.oauth.request('GET',graph+'/'+identity+'/'+edge,headers=headers,params=params)
        rows=response.get('data')
        if not isinstance(rows,list) or len(rows)>12: raise ValueError('Invalid media response')
        ids=[media_id(row.get('id')) for row in rows if platform!='instagram' or row.get('media_type')=='VIDEO']
        def read(identity):
            try:
                endpoint='/insights' if platform=='instagram' else '/video_insights'
                name='views' if platform=='instagram' else 'total_video_views'
                query={'metric':name} if platform=='instagram' else {'metric':name,'period':'lifetime'}
                data=self.oauth.request('GET',graph+'/'+identity+endpoint,headers=headers,params=query)
                return identity,metric(data,name)
            except Exception: return identity,None
        with ThreadPoolExecutor(max_workers=3) as pool:
            for identity,views in pool.map(read,ids):
                if views is None: missing=True
                else: samples[identity]={'views':views}
        paging=response.get('paging',{}); more=bool(paging.get('next')); next_cursor=paging.get('cursors',{}).get('after')
        if more and (not isinstance(next_cursor,str) or not 1<=len(next_cursor)<=2048 or next_cursor==cursor): raise ValueError('Invalid cursor')
        return samples,next_cursor,more,missing
