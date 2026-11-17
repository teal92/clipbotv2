import base64,json,time
from datetime import datetime,timezone
from unittest.mock import Mock
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa,padding
from cryptography.hazmat.primitives import hashes
from fastapi.testclient import TestClient
from server.chat_relay import ChatRelay
from server.store import Store
from server.app import create_app

def relay(tmp_path):
 store=Store(tmp_path/'chat.db');uid=store.create_user('chat@example.com','password-long-enough','Chat');return store,uid,ChatRelay(store,Mock())

@pytest.mark.parametrize('lifetime',[3600,'3600',5183999,'5183999'])
def test_kick_app_token_accepts_numeric_string_and_long_lifetime_with_bounded_cache(tmp_path,lifetime):
 store,uid,r=relay(tmp_path)
 r.oauth.credentials.return_value=('client','secret')
 r.oauth.request.return_value={'access_token':'TOKEN-FIXTURE','expires_in':lifetime}
 before=time.time()
 assert r.headers()=={'Authorization':'Bearer TOKEN-FIXTURE'}
 assert 0<r.token_expires-before<=86401


@pytest.mark.parametrize('lifetime',[True,None,'nan','1e6','-1','9'*50,367*86400])
def test_kick_app_token_rejects_invalid_lifetime_without_caching(tmp_path,lifetime):
 store,uid,r=relay(tmp_path)
 r.oauth.credentials.return_value=('client','secret')
 r.oauth.request.return_value={'access_token':'TOKEN-FIXTURE','expires_in':lifetime}
 with pytest.raises(ValueError):r.headers()
 assert r.app_token is None


def signed(key,body,message='message1'):
 raw=json.dumps(body).encode();stamp=datetime.now(timezone.utc).isoformat();signature=key.sign(message.encode()+b'.'+stamp.encode()+b'.'+raw,padding.PKCS1v15(),hashes.SHA256())
 return raw,{'kick-event-message-id':message,'kick-event-message-timestamp':stamp,'kick-event-signature':base64.b64encode(signature).decode(),'kick-event-subscription-id':'subscription','kick-event-type':'chat.message.sent','kick-event-version':'1'}

def test_signed_chat_is_scoped_ephemeral_and_replay_safe(tmp_path,monkeypatch):
 monkeypatch.setenv('KICK_CHAT_WEBHOOK_ENABLED','1');store,uid,r=relay(tmp_path);key=rsa.generate_private_key(public_exponent=65537,key_size=2048);r.key=key.public_key();r.key_at=time.time()
 r.sources[(uid,'kick','channel')]={'bid':123,'sub':'subscription','expires':time.time()+90}
 raw,headers=signed(key,{'broadcaster':{'user_id':123},'content':'clip that'})
 r.verify(raw,headers);r.verify(raw,headers)
 assert len(r.poll(uid,'kick','channel',0)['messages'])==1
 assert r.poll('other','kick','channel',0)['messages']==[]
 with pytest.raises(ValueError):r.verify(raw+b' ',headers)
 rows=r.feeds[(uid,'kick','channel')];rows[0]['created']=time.time()-61
 assert r.poll(uid,'kick','channel',0)['messages']==[]

def test_webhook_disabled_and_wrong_subscription_do_not_accept(tmp_path,monkeypatch):
 store,uid,r=relay(tmp_path);key=rsa.generate_private_key(public_exponent=65537,key_size=2048);r.key=key.public_key();r.key_at=time.time()
 raw,headers=signed(key,{'broadcaster':{'user_id':123},'content':'clip that'})
 monkeypatch.delenv('KICK_CHAT_WEBHOOK_ENABLED',raising=False)
 with pytest.raises(ValueError):r.verify(raw,headers)
 monkeypatch.setenv('KICK_CHAT_WEBHOOK_ENABLED','1');r.sources[(uid,'kick','channel')]={'bid':123,'sub':'different','expires':time.time()+90};r.verify(raw,headers)
 assert not r.feeds

def test_chat_routes_require_paired_device_and_signed_webhook(tmp_path):
 store,uid,r=relay(tmp_path);app=create_app(store,origin='http://testserver')
 with TestClient(app) as client:
  assert client.get('/api/worker/chat?platform=kick&login=channel').status_code==401
  assert client.post('/api/events/kick/chat',json={}).status_code==403
  token=store.connect_worker(store.new_pairing(uid))
  response=client.get('/api/worker/chat?platform=kick&login=channel',headers={'Authorization':'Bearer '+token})
  assert response.json()['messages']==[] and response.json()['status']=='unavailable'

def test_expiry_closes_chat_connection(tmp_path):
 store,uid,r=relay(tmp_path);watcher=Mock();stop=Mock();r.sources[(uid,'twitch','channel')]={'expires':time.time()-1,'watcher':watcher,'stop':stop}
 r.prune();watcher.close.assert_called_once();stop.set.assert_called_once();assert not r.sources


def test_feed_generation_resets_old_service_cursor(tmp_path):
 store,uid,r=relay(tmp_path);r.sources[(uid,'kick','channel')]={'bid':123,'sub':'subscription','expires':time.time()+90};r.add((uid,'kick','channel'),'new message')
 data=r.poll(uid,'kick','channel',100000,'old-process')
 assert data['messages'][0]['text']=='new message' and data['generation']==r.generation

def test_owned_subscriptions_survive_restart_for_cleanup(tmp_path):
 store,uid,r=relay(tmp_path)
 with store.connection() as db:db.execute('INSERT INTO chat_owned_subscriptions VALUES(?,?)',(123,'owned'))
 restored=ChatRelay(store,Mock());assert restored.subscriptions[123]=='owned' and 123 in restored.owned_subscriptions
 restored.headers=lambda:{'Authorization':'Bearer test'};restored.cleanup_subscriptions()
 assert not restored.subscriptions
 with store.connection() as db:assert db.execute('SELECT count(*) FROM chat_owned_subscriptions').fetchone()[0]==0


def test_stopping_scouts_removes_live_chat_sources(tmp_path):
 store,uid,r=relay(tmp_path);watcher=Mock();stop=Mock();r.sources[(uid,'twitch','channel')]={'expires':time.time()+90,'watcher':watcher,'stop':stop}
 r.validate_sources();assert not r.sources;watcher.close.assert_called_once()
