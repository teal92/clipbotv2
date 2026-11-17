"""Strict, account-owned settings for rolling capture triggers."""
import copy
import json
import secrets
import time
from fastapi import APIRouter, HTTPException, Request

DEFAULT_TRIGGER_SETTINGS = {'beforeSeconds':20,'afterSeconds':20,'cooldownSeconds':60,'audioEnabled':True,'audioRiseDb':10,'speechEnabled':True,'chatEnabled':True,'chatSpikeEnabled':True,'chatSpikeMultiplier':3,'rules':[{'phrase':'no way','source':'speech','priority':'high'},{'phrase':'clip that','source':'chat','priority':'high'}]}

def default_trigger_settings():
    return copy.deepcopy(DEFAULT_TRIGGER_SETTINGS)

def validate_trigger_settings(values):
    if not isinstance(values,dict) or set(values)!=set(DEFAULT_TRIGGER_SETTINGS):
        raise ValueError('Choose supported trigger settings only.')
    for key,low,high in [('beforeSeconds',10,45),('afterSeconds',5,45),('cooldownSeconds',30,300),('audioRiseDb',1,40),('chatSpikeMultiplier',2,20)]:
        if type(values[key]) is not int or not low<=values[key]<=high:
            raise ValueError(f'{key} must be a whole number from {low} to {high}.')
    if not 15<=values['beforeSeconds']+values['afterSeconds']<=60:
        raise ValueError('Before and after time must total 15 to 60 seconds.')
    for key in ('audioEnabled','speechEnabled','chatEnabled','chatSpikeEnabled'):
        if type(values[key]) is not bool:raise ValueError('Trigger switches must be true or false.')
    if not isinstance(values['rules'],list) or len(values['rules'])>20:raise ValueError('Use at most 20 phrase rules.')
    result=copy.deepcopy(values)
    for rule in result['rules']:
        if not isinstance(rule,dict) or set(rule)!={'phrase','source','priority'}:raise ValueError('Choose supported phrase rule fields only.')
        phrase=rule['phrase']
        if not isinstance(phrase,str) or not 1<=len(phrase.strip())<=80 or len(phrase)>80 or any(ord(c)<32 for c in phrase):raise ValueError('Phrases must contain 1 to 80 printable characters.')
        if rule['source'] not in ('speech','chat','either') or rule['priority'] not in ('high','medium','low'):raise ValueError('Choose a supported phrase source and priority.')
        rule['phrase']=phrase.strip()
    return result

class TriggerStore:
    def __init__(self,store):
        self.store=store
        with store.connection() as db:
            db.execute('CREATE TABLE IF NOT EXISTS scout_triggers(user_id TEXT PRIMARY KEY,data TEXT NOT NULL)')
            db.execute('CREATE TABLE IF NOT EXISTS scout_trigger_requests(user_id TEXT NOT NULL,platform TEXT NOT NULL,login TEXT NOT NULL,nonce TEXT NOT NULL,created REAL NOT NULL,PRIMARY KEY(user_id,platform,login))')
    def get(self,uid):
        with self.store.connection() as db:
            if not db.execute('SELECT 1 FROM users WHERE id=?',(uid,)).fetchone():raise ValueError('Account not found.')
            row=db.execute('SELECT data FROM scout_triggers WHERE user_id=?',(uid,)).fetchone()
        return json.loads(row['data']) if row else default_trigger_settings()
    def save(self,uid,values):
        result=validate_trigger_settings(values)
        from .scouts import ScoutStore
        if result['beforeSeconds']+result['afterSeconds']<ScoutStore(self.store).controls(uid)['minClipSeconds']:raise ValueError('Before and after time must cover your minimum clip length.')
        with self.store.connection(atomic=True) as db:
            if not db.execute('SELECT 1 FROM users WHERE id=?',(uid,)).fetchone():raise ValueError('Account not found.')
            db.execute('INSERT OR REPLACE INTO scout_triggers VALUES(?,?)',(uid,json.dumps(result)))
        return result

    def request(self,uid,source):
        from .scouts import source_identity
        source=source_identity(source)
        now=time.time();nonce=secrets.token_hex(16)
        with self.store.connection(atomic=True) as db:
            if not db.execute('SELECT 1 FROM users WHERE id=?',(uid,)).fetchone():raise ValueError('Account not found.')
            db.execute('DELETE FROM scout_trigger_requests WHERE user_id=? AND created<?',(uid,now-120))
            count=db.execute('SELECT count(*) FROM scout_trigger_requests WHERE user_id=?',(uid,)).fetchone()[0]
            exists=db.execute('SELECT 1 FROM scout_trigger_requests WHERE user_id=? AND platform=? AND login=?',(uid,source['platform'],source['login'])).fetchone()
            if count>=40 and not exists:raise ValueError('Too many pending manual triggers.')
            db.execute('INSERT OR REPLACE INTO scout_trigger_requests VALUES(?,?,?,?,?)',(uid,source['platform'],source['login'],nonce,now))
        return {**source,'nonce':nonce,'created':now}
    def requests(self,uid):
        with self.store.connection() as db:
            rows=db.execute('SELECT platform,login,nonce,created FROM scout_trigger_requests WHERE user_id=? AND created>=? ORDER BY created',(uid,time.time()-120)).fetchall()
        return [dict(row) for row in rows]

def build_trigger_router(store,current):
    router=APIRouter();triggers=TriggerStore(store)
    @router.get('/api/scouts/triggers')
    def get(request:Request):
        uid=current(request)['user_id']
        try:return triggers.get(uid)
        except ValueError as error:raise HTTPException(400,str(error))
    @router.put('/api/scouts/triggers')
    def put(values:dict,request:Request):
        uid=current(request,True)['user_id']
        try:return triggers.save(uid,values)
        except ValueError as error:raise HTTPException(400,str(error))
    @router.post('/api/scouts/trigger')
    def manual(source:dict,request:Request):
        uid=current(request,True)['user_id']
        try:return triggers.request(uid,source)
        except ValueError as error:raise HTTPException(400,str(error))
    return router
