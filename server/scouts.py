"""Validated account-owned scout preferences; no media or provider credentials."""
import json,re,time

class ScoutDenied(ValueError): pass
class ScoutStartDenied(ScoutDenied): pass

SOURCE_FIELDS={'platform','login'}
def source_identity(value):
    if not isinstance(value,dict) or set(value)!=SOURCE_FIELDS or value.get('platform') not in ('twitch','kick') or not isinstance(value.get('login'),str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,35}' if value.get('platform')=='kick' else r'[A-Za-z0-9_]{1,35}',value['login']):
        raise ScoutDenied('Choose a valid Twitch or Kick channel.')
    return {'platform':value['platform'],'login':value['login'].lower()}

def limits_in(db,uid):
    from .owner_showcase import showcase_in
    showcase=showcase_in(db,uid)
    if showcase:return {key:showcase[key] for key in ('scouts','favorites','categories')}
    from .billing_modes import entitlement_allowed
    if not entitlement_allowed(db,uid):return {'scouts':0,'favorites':0,'categories':0}
    coverage=db.execute('SELECT scouts,favorites,categories FROM coverage WHERE user_id=?',(uid,)).fetchone()
    billing=db.execute('SELECT status,expires FROM billing_state WHERE user_id=?',(uid,)).fetchone()
    if not coverage or (billing and (billing['status']!='active' or billing['expires']<=time.time())):
        return {'scouts':0,'favorites':0,'categories':0}
    return dict(coverage)

def default_controls():return {'sensitivity':'balanced','captureGate':'balanced','captureSeconds':120,'minClipSeconds':15,'maxClipSeconds':60,'captureCapacity':2}

def empty_config():return {'running':False,'slots':0,'forced':[],'favorites':[],'categories':[]}

class ScoutStore:
    def __init__(self,store):
        self.store=store
        with store.connection() as db:
            db.execute('CREATE TABLE IF NOT EXISTS scout_settings(user_id TEXT PRIMARY KEY,data TEXT NOT NULL,revision TEXT NOT NULL,updated REAL NOT NULL)')
    def save(self,uid,selection,allow_start=True):
        if not isinstance(selection,dict) or not set(empty_config())<=set(selection) or not set(selection)<=set(empty_config())|{'forcedCategories','platformSlots'} or type(selection['running']) is not bool or type(selection['slots']) is not int or not 0<=selection['slots']<=40:
            raise ScoutDenied('Choose valid monitoring settings.')
        result={'running':selection['running'],'slots':selection['slots']}
        allocation=selection.get('platformSlots')
        if allocation is not None:
            if not isinstance(allocation,dict) or set(allocation)!={'twitch','kick'} or any(type(v) is not int or not 0<=v<=40 for v in allocation.values()) or sum(allocation.values())!=selection['slots']:
                raise ScoutDenied('Platform scout counts must add up to your number of scouts.')
            result['platformSlots']=dict(allocation)
        for key in ('forced','favorites'):
            values=selection[key]
            if not isinstance(values,list) or len(values)>40:raise ScoutDenied('Too many channel selections.')
            result[key]=[source_identity(item) for item in values]
            identities={(v['platform'],v['login']) for v in result[key]}
            if len(identities)!=len(values):raise ScoutDenied('Select each channel once.')
        categories=selection['categories']
        if not isinstance(categories,list) or len(categories)>25:raise ScoutDenied('Too many categories.')
        result['categories']=[]
        for item in categories:
            if not isinstance(item,dict) or set(item)!={'platform','id','name'} or item['platform'] not in ('twitch','kick') or not isinstance(item['id'],str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,100}',item['id']) or not isinstance(item['name'],str) or not 1<=len(item['name'])<=100 or any(ord(c)<32 for c in item['name']):raise ScoutDenied('Choose a valid category.')
            result['categories'].append(dict(item))
        if len({(v['platform'],v['id']) for v in result['categories']})!=len(categories):raise ScoutDenied('Select each category once.')
        forced_categories=selection.get('forcedCategories',[])
        if not isinstance(forced_categories,list) or len(forced_categories)>40:raise ScoutDenied('Too many forced categories.')
        result['forcedCategories']=[]
        for item in forced_categories:
            if not isinstance(item,dict) or set(item)!={'platform','id','name'} or item['platform'] not in ('twitch','kick') or not isinstance(item['id'],str) or not item['id'].isdigit() or len(item['id'])>20 or not isinstance(item['name'],str) or not 1<=len(item['name'])<=100 or any(ord(c)<32 for c in item['name']):raise ScoutDenied('Choose a valid forced category.')
            result['forcedCategories'].append(dict(item))
        if len({(v['platform'],v['id']) for v in result['forcedCategories']})!=len(forced_categories):raise ScoutDenied('Force each category once.')
        with self.store.connection(atomic=True) as db:
            existing=db.execute('SELECT data FROM scout_settings WHERE user_id=?',(uid,)).fetchone()
            running=json.loads(existing['data'])['running'] if existing else False
            if not allow_start and result['running'] and not running:raise ScoutStartDenied('Use Start ClipBot to start a supported companion.')
            limits=limits_in(db,uid)
            if not db.execute('SELECT 1 FROM users WHERE id=?',(uid,)).fetchone():raise ScoutDenied('Account not found.')
            if result['slots']>limits['scouts'] or len(result['forced'])+len(forced_categories)>(40 if 'platformSlots' in result else result['slots']) or len(result['favorites'])>limits['favorites'] or len(categories)>limits['categories']:raise ScoutDenied('These selections exceed your current plan allowance.')
            if result['running'] and result['slots']==0:raise ScoutDenied('Choose at least one permitted scout slot.')
            import secrets
            db.execute('INSERT OR REPLACE INTO scout_settings VALUES(?,?,?,?)',(uid,json.dumps(result),secrets.token_hex(16),time.time()))
            from .debug_sessions import DebugSessions
            DebugSessions.transition_in(db,uid,running,result['running'],result)
        return self.snapshot(uid)
    def snapshot(self,uid):
        with self.store.connection() as db:
            row=db.execute('SELECT * FROM scout_settings WHERE user_id=?',(uid,)).fetchone();limits=limits_in(db,uid)
        config=json.loads(row['data']) if row else empty_config()
        config.setdefault('forcedCategories',[])
        config.setdefault('platformSlots',{'twitch':(config['slots']+1)//2,'kick':config['slots']//2})
        effective={**config,'slots':min(config['slots'],limits['scouts']),'favorites':config['favorites'][:limits['favorites']],'categories':config['categories'][:limits['categories']]}
        effective['forced']=config['forced'][:effective['slots']]
        effective['forcedCategories']=config['forcedCategories'][:max(0,effective['slots']-len(effective['forced']))]
        if 'platformSlots' in config:
            twitch=min(config['platformSlots']['twitch'],effective['slots'])
            effective['platformSlots']={'twitch':twitch,'kick':min(config['platformSlots']['kick'],effective['slots']-twitch)}
        effective['running']=config['running'] and effective['slots']>0
        return {'configuration':config,'effective':effective,'limits':limits,'revision':row['revision'] if row else '', 'controls':self.controls(uid)}

    def controls(self,uid):
        with self.store.connection() as db:
            db.execute('CREATE TABLE IF NOT EXISTS scout_controls(user_id TEXT PRIMARY KEY,data TEXT NOT NULL)')
            row=db.execute('SELECT data FROM scout_controls WHERE user_id=?',(uid,)).fetchone()
        return json.loads(row['data']) if row else default_controls()
    def save_controls(self,uid,values):
        defaults=default_controls()
        if not isinstance(values,dict) or set(values)!=set(defaults) or values['sensitivity'] not in ('loose','balanced','strict') or values['captureGate'] not in ('review','balanced','strict'):raise ScoutDenied('Choose supported scout controls.')
        for key,low,high in [('captureCapacity',1,40),('captureSeconds',30,300),('minClipSeconds',15,60),('maxClipSeconds',15,60)]:
            if type(values[key]) is not int or not low<=values[key]<=high:raise ScoutDenied('Choose a bounded capture or clip length.')
        if values['minClipSeconds']>values['maxClipSeconds'] or values['maxClipSeconds']>values['captureSeconds']:raise ScoutDenied('Clip length must fit inside the capture window.')
        from .trigger_settings import TriggerStore
        trigger=TriggerStore(self.store).get(uid)
        if values['minClipSeconds']>trigger['beforeSeconds']+trigger['afterSeconds']:raise ScoutDenied('Increase before/after time before selecting this minimum clip length.')
        self.controls(uid)
        with self.store.connection(atomic=True) as db:
            if not db.execute('SELECT 1 FROM users WHERE id=?',(uid,)).fetchone():raise ScoutDenied('Account not found.')
            db.execute('INSERT OR REPLACE INTO scout_controls VALUES(?,?)',(uid,json.dumps(values)))
        return self.snapshot(uid)
