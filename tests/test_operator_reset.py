import tempfile,unittest
from pathlib import Path
from fastapi import FastAPI
from fastapi.testclient import TestClient
from server.store import Store
class OperatorResetTests(unittest.TestCase):
 def test_callback_requires_owner_confirmation_and_no_token_response(self):
  from server.customer_admin import build_operator_router
  with tempfile.TemporaryDirectory() as directory:
   store=Store(Path(directory)/'db');uid=store.create_user('a@example.com','test-password','A')
   called=[]
   def reset(uid):called.append(uid);return {'token':'never-return-this'}
   app=FastAPI();app.include_router(build_operator_router(store,None,service_key='k'*40,reset_request=reset));client=TestClient(app);headers={'Authorization':'Bearer '+'k'*40}
   self.assertEqual(client.post('/api/operator/customers/'+uid+'/reset',headers=headers,json={}).status_code,400);self.assertEqual(called,[])
   result=client.post('/api/operator/customers/'+uid+'/reset',headers=headers,json={'approved':True})
   self.assertEqual(result.status_code,200);self.assertEqual(called,[uid]);self.assertNotIn('token',result.text)
 def test_private_key_file_fallback(self):
  from server.customer_admin import operator_key
  with tempfile.TemporaryDirectory() as directory:
   path=Path(directory)/'key';path.write_text('k'*40);self.assertEqual(operator_key('',path),'k'*40)
