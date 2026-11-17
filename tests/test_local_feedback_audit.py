import hashlib,hmac,json,time
from fastapi.testclient import TestClient
from server.store import Store
from server.app import create_app
from server.feedback_receipt import issue_receipt

def test_receipt_is_device_bound_and_has_no_key(tmp_path):
 store=Store(tmp_path/'receipt.db');uid=store.create_user('receipt@example.com','a-good-long-password','Receipt');token=store.connect_worker(store.new_pairing(uid))
 receipt=issue_receipt(store,uid,'a'*32,'approve')
 payload={k:v for k,v in receipt.items() if k!='signature'}
 key=hashlib.sha256(token.encode()).digest()
 assert hmac.compare_digest(receipt['signature'],hmac.new(key,json.dumps(payload,sort_keys=True,separators=(',',':')).encode(),hashlib.sha256).hexdigest())
 assert token not in json.dumps(receipt) and hashlib.sha256(token.encode()).hexdigest() not in json.dumps(receipt)
 assert issue_receipt(store,'foreign','a'*32,'approve') is None

def test_local_review_retains_only_workflow_audit_and_pauses_global_collection(tmp_path):
 store=Store(tmp_path/'local.db');uid=store.create_user('local@example.com','a-good-long-password','Local');store.accept_beta(uid)
 with store.connection() as db:db.execute('INSERT INTO candidates VALUES(?,?,?)',('a'*32,uid,json.dumps({'id':'a'*32})))
 token=store.connect_worker(store.new_pairing(uid));app=create_app(store,origin='http://testserver')
 with TestClient(app) as c:
  login=c.post('/api/auth/login',json={'email':'local@example.com','password':'a-good-long-password'},headers={'Origin':'http://testserver'})
  headers={'Origin':'http://testserver','X-CSRF-Token':login.json()['csrfToken']}
  body={'candidate_id':'a'*32,'decision':'reject','localLearning':True,'reasons':[],'justification':''}
  assert c.post('/api/reviews',json={**body,'justification':'PRIVATE NOTE'},headers=headers).status_code==422
  result=c.post('/api/reviews',json=body,headers=headers)
  assert result.status_code==200 and result.json()['localFeedbackReceipt']['userId']==uid
  with store.connection() as db:
   audit=json.loads(db.execute('SELECT data FROM reviews WHERE user_id=?',(uid,)).fetchone()['data'])
   assert audit['user_feedback']=={'decision':'reject','reasons':[],'justification':''}
   assert db.execute('SELECT COUNT(*) FROM shared_feedback').fetchone()[0]==0
