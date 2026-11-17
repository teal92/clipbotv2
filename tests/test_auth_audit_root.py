from server.legal import POLICY_VERSION
from fastapi.testclient import TestClient
from server.app import create_app
from server.store import Store
def test_distributed_attempts_on_one_account_are_bounded(tmp_path):
 app=create_app(Store(tmp_path/'auth.db'),origin='http://testserver')
 for i in range(21):
  with TestClient(app,client=(f'198.51.100.{i+1}',5000)) as c:
   result=c.post('/api/auth/login',json={'email':'missing@example.com','password':'a-long-wrong-password'},headers={'Origin':'http://testserver'})
   assert result.status_code==(401 if i<20 else 429)
def test_signup_requires_current_policy_before_creating_account(tmp_path):
 store=Store(tmp_path/'signup.db');app=create_app(store,origin='http://testserver',local_signup=True)
 with TestClient(app,client=('127.0.0.1',5000)) as c:
  data={'email':'new@example.com','password':'StrongClipBot!2026','name':'New'}
  assert c.post('/api/auth/signup',json=data,headers={'Origin':'http://testserver'}).status_code==422
  result=c.post('/api/auth/signup',json={**data,'termsVersion':POLICY_VERSION},headers={'Origin':'http://testserver'})
  assert result.status_code==201
  with store.connection() as db:assert db.execute('SELECT COUNT(*) FROM legal_acceptances').fetchone()[0]==1
def test_owner_website_routes_removed_and_policies_public(tmp_path):
 app=create_app(Store(tmp_path/'routes.db'),origin='http://testserver')
 with TestClient(app) as c:
  assert c.get('/api/admin/metrics').status_code==404
  assert c.get('/admin').status_code==404
  for path in ('/terms','/privacy','/acceptable-use'):assert c.get(path).status_code==200
