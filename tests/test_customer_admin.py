import json, tempfile, unittest
from pathlib import Path
from fastapi import FastAPI
from fastapi.testclient import TestClient
from server.store import Store
class CustomerAdminTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
  self.store=Store(Path(self.tmp.name)/'db.sqlite');self.uid=self.store.create_user('one@example.com','sample-test-password','One')
  self.store.set_coverage(self.uid,review_daily=1,user_monthly=100,scouts=1,favorites=1,categories=1,posts=1)
 def test_projection_and_real_cap(self):
  from server.customer_admin import list_customers
  with self.store.connection() as db:db.execute('INSERT INTO jobs VALUES(?,?,?,?,?,?,?,?,?)',(self.uid,'one','2026-10-13','2026-10',0,100,20,30,'settled'))
  result=list_customers(self.store,now=1791936000);row=result['customers'][0]
  self.assertEqual(row['email'],'one@example.com');self.assertEqual(row['passwordStatus'],'Set; never readable')
  self.assertEqual(row['usage']['tokens7Days'],50);self.assertIn('monthly_budget',row['limitsReached'])
  self.assertEqual(row['abuseStatus'],'Not assessed');self.assertNotIn('password',row);self.assertNotIn('password_hash',json.dumps(result))
 def test_credential_and_reset_unavailable(self):
  from server.customer_admin import build_operator_router
  app=FastAPI();app.include_router(build_operator_router(self.store,None,service_key='s'*40));client=TestClient(app)
  self.assertEqual(client.get('/api/operator/customers').status_code,401)
  self.assertEqual(client.get('/api/operator/customers',headers={'Authorization':'Bearer wrong'}).status_code,401)
  headers={'Authorization':'Bearer '+'s'*40};self.assertEqual(client.get('/api/operator/customers',headers=headers).status_code,200)
  self.assertEqual(client.post('/api/operator/customers/'+self.uid+'/reset',headers=headers,json={'approved':True}).status_code,409)
  self.assertTrue(self.store.authenticate('one@example.com','sample-test-password'))
 def test_disabled_without_key(self):
  from server.customer_admin import build_operator_router
  app=FastAPI();app.include_router(build_operator_router(self.store,None,service_key=''))
  self.assertEqual(TestClient(app).get('/api/operator/customers').status_code,404)

 def test_edge_diagnostics_are_private_and_do_not_return_client_identity(self):
  from server.customer_admin import build_operator_router
  app=FastAPI();app.include_router(build_operator_router(self.store,None,service_key='s'*40))
  client=TestClient(app,client=('10.0.0.7',443))
  assert client.get('/api/operator/edge-status').status_code==401
  headers={'Authorization':'Bearer '+'s'*40,'CF-Connecting-IP':'8.8.8.8','CF-Ray':'0123456789abcdef-IAD'}
  response=client.get('/api/operator/edge-status',headers=headers)
  assert response.status_code==200
  result=response.json()
  assert result['cloudflareClientPublic'] and result['cloudflareRayPresent']
  assert not result['forgedClientHeaderReachedOrigin']
  assert not result['trustedClientAttribution']
  assert '8.8.8.8' not in response.text
  assert 's'*40 not in response.text
  assert client.get('/api/operator/edge-status?probe_ip=invalid',headers=headers).status_code==422
