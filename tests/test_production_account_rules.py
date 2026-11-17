from fastapi.testclient import TestClient
from server.app import create_app
from server.store import Store
from server.legal import POLICY_VERSION

def test_signup_rejects_weak_password_and_claims_unique_display_username(tmp_path):
 store=Store(tmp_path/'users.db');store.create_user('legacy@example.com','legacy-long-password','Reserved')
 app=create_app(store,origin='http://testserver',local_signup=True)
 with TestClient(app,client=('127.0.0.1',5000)) as c:
  body={'email':'new@example.com','name':'FreshName','password':'justlowercaseforever','termsVersion':POLICY_VERSION}
  assert c.post('/api/auth/signup',json=body,headers={'Origin':'http://testserver'}).status_code==422
  body['password']='StrongClipBot!2026'
  assert c.post('/api/auth/signup',json={**body,'name':'RESERVED'},headers={'Origin':'http://testserver'}).status_code==409
  result=c.post('/api/auth/signup',json=body,headers={'Origin':'http://testserver'});assert result.status_code==201
  user=c.get('/api/account').json()['user'];assert user['name']==user['username']=='freshname'
  assert user['usernameChangedAt'] and user['usernameChangeAvailableAt']>user['usernameChangedAt']
  csrf=c.get('/api/account').json()['csrfToken']
  assert c.patch('/api/account/profile',json={'username':'anothername'},headers={'Origin':'http://testserver','X-CSRF-Token':csrf}).status_code==409
  assert c.post('/api/auth/signup',json={**body,'email':'other@example.com','name':'FRESHNAME'},headers={'Origin':'http://testserver'}).status_code==409

def test_password_change_enforces_policy_without_rejecting_legacy_login(tmp_path):
 store=Store(tmp_path/'legacy.db');uid=store.create_user('legacy@example.com','legacy-long-password','Legacy')
 app=create_app(store,origin='http://testserver')
 with TestClient(app) as c:
  origin={'Origin':'http://testserver'}
  assert c.post('/api/auth/login',json={'email':'legacy@example.com','password':'legacy-long-password'},headers=origin).status_code==200
  headers={**origin,'X-CSRF-Token':c.get('/api/account').json()['csrfToken']}
  for weak in ['alllowercaseforever','UPPERCASEONLY123!','NoNumberLong!','NoSymbolLong123','Password123!']:
   assert c.post('/api/account/password',json={'currentPassword':'legacy-long-password','newPassword':weak},headers=headers).status_code==422
   assert store.authenticate('legacy@example.com','legacy-long-password')==uid
  assert c.post('/api/account/password',json={'currentPassword':'legacy-long-password','newPassword':'StrongClipBot!2026'},headers=headers).status_code==200
  assert store.authenticate('legacy@example.com','StrongClipBot!2026')==uid


def test_existing_assigned_username_receives_migration_cooldown(tmp_path):
 import sqlite3
 path=tmp_path/'migration.db'
 db=sqlite3.connect(path)
 db.executescript("CREATE TABLE users(id TEXT PRIMARY KEY,email TEXT UNIQUE NOT NULL,password TEXT NOT NULL,name TEXT NOT NULL,created REAL NOT NULL); CREATE TABLE user_profiles(user_id TEXT PRIMARY KEY,username TEXT COLLATE NOCASE UNIQUE,avatar TEXT NOT NULL DEFAULT ''); INSERT INTO users VALUES('user','old@example.com','unused','OldName',1); INSERT INTO user_profiles VALUES('user','assigned_name','');")
 db.commit();db.close()
 store=Store(path);user=store.user('user')
 assert user['usernameChangedAt'] is not None and user['name']=='assigned_name'
 from server.store import UsernameChangeUnavailable
 import pytest
 with pytest.raises(UsernameChangeUnavailable):store.update_profile('user','new_assigned')
