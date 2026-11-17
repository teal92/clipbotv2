"""Account-scoped ephemeral chat feeds. Credentials never reach the companion."""
import base64,json,os,re,threading,time,secrets
from collections import OrderedDict,deque
from datetime import datetime
from fastapi import APIRouter,Request,HTTPException
from cryptography.hazmat.primitives import hashes,serialization
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric import padding,rsa
from .worker_jobs import device_user,WorkerDenied
from .scouts import source_identity,ScoutStore
from .discovery import Directory

class ChatRelay:
 def __init__(self,store,oauth):
  self.store=store;self.oauth=oauth;self.lock=threading.RLock();self.sources={};self.feeds={};self.replay=OrderedDict();self.sequence=0;self.generation=secrets.token_hex(16);self.key=None;self.key_at=0;self.app_token=None;self.token_expires=0;self.subscriptions={};self.owned_subscriptions=set();self.stop=threading.Event();self.thread=None;self.subscription_lock=threading.Lock()
  with store.connection() as db:
   db.execute('CREATE TABLE IF NOT EXISTS chat_owned_subscriptions(broadcaster INTEGER PRIMARY KEY,subscription TEXT NOT NULL)')
   for row in db.execute('SELECT broadcaster,subscription FROM chat_owned_subscriptions'):self.subscriptions[row['broadcaster']]=row['subscription'];self.owned_subscriptions.add(row['broadcaster'])
 def prune(self):
  now=time.time()
  for key,value in list(self.sources.items()):
   if value['expires']<now:
    if value.get('watcher'):value['stop'].set();value['watcher'].close()
    self.sources.pop(key,None)
  for key,rows in list(self.feeds.items()):
   while rows and rows[0]['created']<now-60:rows.popleft()
   if not rows:self.feeds.pop(key,None)
  while self.replay and next(iter(self.replay.values()))<now-300:self.replay.popitem(last=False)
 def cleanup_subscriptions(self):
  with self.subscription_lock:
   with self.lock:used={v.get('bid') for v in self.sources.values()};obsolete=[(bid,sub) for bid,sub in self.subscriptions.items() if bid not in used and bid in self.owned_subscriptions][:100]
   if not obsolete:return
   try:
    self.oauth.request('DELETE','https://api.kick.com/public/v1/events/subscriptions',headers=self.headers(),params=[('id',sub) for bid,sub in obsolete],allow_empty=True)
    with self.lock:
     for bid,sub in obsolete:
      self.subscriptions.pop(bid,None);self.owned_subscriptions.discard(bid)
      with self.store.connection() as db:db.execute('DELETE FROM chat_owned_subscriptions WHERE broadcaster=? AND subscription=?',(bid,sub))
   except Exception:pass
 def validate_sources(self):
  with self.lock:owners={(k[0],k[1]) for k in self.sources}
  for uid,platform in owners:
   try:
    cfg=ScoutStore(self.store).snapshot(uid)['effective'];record=self.oauth.vault.load(uid,platform)
    allowed=cfg['running'] and cfg.get('platformSlots',{}).get(platform,cfg['slots'])>0 and record is not None and (platform!='twitch' or 'chat:read' in record['tokens'].get('scopes',[]))
   except Exception:allowed=False
   if not allowed:
    with self.lock:
     for key,value in list(self.sources.items()):
      if key[:2]==(uid,platform):
       if value.get('watcher'):value['stop'].set();value['watcher'].close()
       self.sources.pop(key,None)
 def start(self):
  def clean():
   while not self.stop.wait(10):
    with self.lock:self.prune()
    self.validate_sources();self.cleanup_subscriptions()
  self.thread=threading.Thread(target=clean,daemon=True);self.thread.start()
 def add(self,key,text):
  with self.lock:
   self.sequence+=1;self.feeds.setdefault(key,deque(maxlen=500)).append({'id':self.sequence,'text':text[:500],'created':time.time()})
 def headers(self):
  if not self.app_token or self.token_expires<time.time()+60:
   client,secret=self.oauth.credentials('kick');data=self.oauth.request('POST','https://id.kick.com/oauth/token',data={'grant_type':'client_credentials','client_id':client,'client_secret':secret})
   access=data.get('access_token');raw_duration=data.get('expires_in')
   if type(raw_duration) is not int and not (isinstance(raw_duration,str) and raw_duration.isascii() and raw_duration.isdigit() and len(raw_duration)<12):raise ValueError('Chat unavailable.')
   duration=int(raw_duration)
   if not isinstance(access,str) or not 1<=len(access)<=16000 or not 60<=duration<=366*86400:raise ValueError('Chat unavailable.')
   # Kick may return a numeric string or a token valid beyond one day. Keep
   # the cache bounded to one day rather than rejecting valid authorization.
   self.app_token=access;self.token_expires=time.time()+min(duration,86400)
  return {'Authorization':'Bearer '+self.app_token}
 def subscribe(self,uid,source):
  source=source_identity(source);platform=source['platform'];login=source['login'];key=(uid,platform,login)
  cfg=ScoutStore(self.store).snapshot(uid)['effective']
  if not cfg['running'] or cfg.get('platformSlots',{}).get(platform,cfg['slots'])<=0:raise ValueError('Scouts are disabled.')
  with self.lock:
   self.prune();old=self.sources.get(key)
   if old and old.get('watcher') and old['watcher'].status=='unavailable' and old.get('created',0)<time.time()-30:
    old['stop'].set();old['watcher'].close();self.sources.pop(key,None);old=None
   if old:old['expires']=time.time()+90;return {'status':'connecting'}
   if sum(k[0]==uid for k in self.sources)>=40 or len(self.sources)>=1000:raise ValueError('Chat connections are full.')
   self.sources[key]={'expires':time.time()+90,'pending':True}
  try:
   if platform=='twitch':
    from worker.chat_inputs import ChatWatcher
    record=self.oauth.vault.load(uid,'twitch')
    if not record or 'chat:read' not in record['tokens'].get('scopes',[]):raise ValueError('permissions_missing')
    headers=Directory(self.oauth).access(uid,'twitch');users=self.oauth.request('GET','https://api.twitch.tv/helix/users',headers=headers)['data'];nick=users[0]['login']
    record=self.oauth.vault.load(uid,'twitch');stop=threading.Event();watcher=ChatWatcher(source,lambda text:self.add(key,text),stop,authentication=(nick,record['tokens']['access_token']))
    with self.lock:self.sources[key]={'expires':time.time()+90,'created':time.time(),'watcher':watcher,'stop':stop}
    threading.Thread(target=watcher.run,daemon=True).start();return {'status':'connecting'}
   if os.getenv('KICK_CHAT_WEBHOOK_ENABLED')!='1':raise ValueError('service_setup')
   rows=self.oauth.request('GET','https://api.kick.com/public/v1/channels',headers=Directory(self.oauth).access(uid,'kick'),params={'slug':login})['data'];row=next(r for r in rows if r.get('slug')==login);bid=row['broadcaster_user_id']
   if type(bid) is not int or bid<=0:raise ValueError()
   with self.subscription_lock:
    headers=self.headers()
    if bid in self.subscriptions:
     current=self.oauth.request('GET','https://api.kick.com/public/v1/events/subscriptions',headers=headers,params={'broadcaster_user_id':bid}).get('data',[])
     if not any(r.get('id')==self.subscriptions[bid] and r.get('event')=='chat.message.sent' and r.get('broadcaster_user_id')==bid for r in current):
      self.subscriptions.pop(bid,None);self.owned_subscriptions.discard(bid)
      with self.store.connection() as db:db.execute('DELETE FROM chat_owned_subscriptions WHERE broadcaster=?',(bid,))
    if bid not in self.subscriptions:
     if len(self.subscriptions)>=1000:raise ValueError()
     existing=self.oauth.request('GET','https://api.kick.com/public/v1/events/subscriptions',headers=headers,params={'broadcaster_user_id':bid}).get('data',[])
     sub=next((r.get('id') for r in existing if r.get('event')=='chat.message.sent' and r.get('broadcaster_user_id')==bid),None)
     created=False
     if not sub:
      result=self.oauth.request('POST','https://api.kick.com/public/v1/events/subscriptions',headers=headers,json={'broadcaster_user_id':bid,'method':'webhook','events':[{'name':'chat.message.sent','version':1}]}).get('data',[])
      sub=next((r.get('subscription_id') for r in result if r.get('name')=='chat.message.sent' and not r.get('error')),None);created=True
     if not isinstance(sub,str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,100}',sub):raise ValueError()
     self.subscriptions[bid]=sub
     if created:
      self.owned_subscriptions.add(bid)
      with self.store.connection() as db:db.execute('INSERT OR REPLACE INTO chat_owned_subscriptions VALUES(?,?)',(bid,sub))
    with self.lock:self.sources[key]={'bid':bid,'sub':self.subscriptions[bid],'expires':time.time()+90}
   return {'status':'connecting'}
  except Exception as error:
   with self.lock:self.sources.pop(key,None)
   return {'status':'unavailable','reason':'permissions_missing' if str(error)=='permissions_missing' else 'service_setup'}
 def verify(self,raw,headers):
  if len(raw)>16384:raise ValueError('Invalid chat event.')
  if os.getenv('KICK_CHAT_WEBHOOK_ENABLED')!='1':raise ValueError('Chat event feed disabled.')
  message=headers.get('kick-event-message-id','');stamp=headers.get('kick-event-message-timestamp','');signature=headers.get('kick-event-signature','')
  if not re.fullmatch(r'[A-Za-z0-9_-]{1,100}',message) or len(stamp)>50 or len(signature)>1024:raise ValueError('Invalid chat event.')
  try:
   if abs(time.time()-datetime.fromisoformat(stamp.replace('Z','+00:00')).timestamp())>300:raise ValueError()
   with self.lock:
    if self.key is None or self.key_at<time.time()-3600:
     if self.key_at>time.time()-30:raise ValueError()
     self.key_at=time.time()
     pem=self.oauth.request('GET','https://api.kick.com/public/v1/public-key')['data']['public_key'];key=serialization.load_pem_public_key(pem.encode()) if isinstance(pem,str) and len(pem)<8192 else None
     if not isinstance(key,rsa.RSAPublicKey):raise ValueError()
     self.key=key;self.key_at=time.time()
    key=self.key
   payload=message.encode()+b'.'+stamp.encode()+b'.'+raw;decoded=base64.b64decode(signature,validate=True)
   try:key.verify(decoded,payload,padding.PKCS1v15(),hashes.SHA256())
   except InvalidSignature:
    with self.lock:
     if self.key_at>time.time()-30:raise
     self.key_at=time.time();pem=self.oauth.request('GET','https://api.kick.com/public/v1/public-key')['data']['public_key'];replacement=serialization.load_pem_public_key(pem.encode())
     if not isinstance(replacement,rsa.RSAPublicKey):raise ValueError()
     self.key=replacement
    replacement.verify(decoded,payload,padding.PKCS1v15(),hashes.SHA256())
   body=json.loads(raw)
   if headers.get('kick-event-type')!='chat.message.sent' or headers.get('kick-event-version')!='1':return
   bid=body.get('broadcaster',{}).get('user_id');text=body.get('content');sub=headers.get('kick-event-subscription-id')
   if type(bid) is not int or not isinstance(text,str) or not 1<=len(text)<=2000:raise ValueError()
   with self.lock:
    self.prune()
    if message in self.replay:return
    if len(self.replay)>=50000:raise ValueError()
    self.replay[message]=time.time()
    for key,value in self.sources.items():
     if key[1]=='kick' and value.get('bid')==bid and value.get('sub')==sub:self.add(key,text)
  except Exception:raise ValueError('Chat event verification failed.') from None
 def poll(self,uid,platform,login,cursor,generation=None):
  source_identity({'platform':platform,'login':login});key=(uid,platform,login)
  with self.lock:
   self.prune();source=self.sources.get(key)
   if generation!=self.generation:cursor=0
   if not source:return {'status':'unavailable','messages':[],'cursor':cursor,'generation':self.generation}
   rows=[r for r in self.feeds.get(key,[]) if r['created']>time.time()-30 and r['id']>cursor]
   status=source['watcher'].status if source.get('watcher') else 'connected' if self.feeds.get(key) else 'connecting'
   return {'status':status,'generation':self.generation,'messages':[{'id':r['id'],'text':r['text'],'created':r['created']} for r in rows],'cursor':max([cursor]+[r['id'] for r in rows])}
 def close(self):
  self.stop.set()
  if self.thread:self.thread.join(timeout=1)
  with self.lock:
   for value in self.sources.values():
    if value.get('watcher'):value['stop'].set();value['watcher'].close()
   self.sources.clear();self.feeds.clear()
  self.cleanup_subscriptions()

def build_chat_router(store,current,oauth):
 router=APIRouter();relay=ChatRelay(store,oauth);router.chat_relay=relay
 def uid(request):
  header=request.headers.get('authorization','');token=header[7:] if header.startswith('Bearer ') else ''
  with store.connection() as db:
   try:return device_user(db,token)
   except WorkerDenied:raise HTTPException(401,'Reconnect the companion.')
 @router.post('/api/worker/chat/subscribe')
 def subscribe(source:dict,request:Request):
  owner=uid(request)
  try:return relay.subscribe(owner,source)
  except ValueError as error:raise HTTPException(409,str(error))
 @router.get('/api/worker/chat')
 def poll(request:Request,platform:str,login:str,cursor:int=0,generation:str=''):
  owner=uid(request)
  if platform not in ('twitch','kick') or not 0<=cursor<=2**63-1:raise HTTPException(422,'Invalid chat source.')
  try:return relay.poll(owner,platform,login,cursor,generation[:32])
  except ValueError:raise HTTPException(422,'Invalid chat source.')
 @router.post('/api/events/kick/chat')
 async def event(request:Request):
  try:
   from starlette.concurrency import run_in_threadpool
   await run_in_threadpool(relay.verify,await request.body(),request.headers)
  except ValueError:raise HTTPException(403,'Chat event verification failed.')
  return {'ok':True}
 return router
