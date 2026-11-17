import json,time
from server.store import Store
from server.admin import metrics

def test_customer_plans_and_all_owned_usage_exclude_owner_and_test_ids(tmp_path,monkeypatch):
 s=Store(tmp_path/'scope.db');now=time.time()
 owner=s.create_user('owner@example.com','synthetic-password','Owner')
 test=s.create_user('test@example.com','synthetic-password','Test')
 customers=[s.create_user(f'customer{i}@example.com','synthetic-password',f'Customer{i}') for i in range(5)]
 monkeypatch.setenv('CLIPBOT_ADMIN_USER_ID',owner)
 monkeypatch.setenv('CLIPBOT_METRICS_EXCLUDED_USER_IDS',test)
 for uid in [owner,test,*customers]:
  with s.connection() as db:
   db.execute("INSERT INTO jobs(user_id,job_id,day,month,input_tokens,output_tokens,reserved,state) VALUES(?,?,?,?,?,?,?,?)",(uid,uid,'2026-10-14','2026-10',100,20,0,'settled'))
   db.execute('INSERT INTO beta_acceptance VALUES(?,?,?)',(uid,'beta-feedback-v1',now))
 for uid,plan in zip([owner,test,*customers[:4]],['pro','starter','starter','creator','pro','custom']):
  with s.connection() as db:db.execute('INSERT INTO billing_state(user_id,subscription,customer,plan,status,expires) VALUES(?,?,?,?,?,?)',(uid,'sub_'+uid,'cust_'+uid,plan,'active',now+3600))
 s.development_user()
 with s.connection() as db:db.execute('INSERT INTO shared_feedback VALUES(?,?,?,?)',('unattributed','approve','["Funny"]',now-5))
 data=metrics(s,now=now)
 assert data['registeredUsers']==5
 assert data['customersByPlan']==dict(starter=1,creator=1,pro=1,custom=1)
 assert data['customersWithoutActivePlan']==1
 assert data['inputTokens']==500 and data['outputTokens']==100 and data['completedReviews']==5
 assert data['learning']['betaParticipants']==5
 assert data['sharedDecisions']==0 and data['contributions']['total']==0
 assert data['contributions']['excludedUnattributed']==1
 assert data['metricsScope']=='customers_only' and data['ownerExclusionConfigured'] is True
 serialized=json.dumps(data)
 assert owner not in serialized and test not in serialized and 'owner@example.com' not in serialized
 with s.connection() as db:assert db.execute('SELECT COUNT(*) FROM users').fetchone()[0]==8

def test_empty_and_expired_plans_are_explicit_not_fake_custom(tmp_path,monkeypatch):
 s=Store(tmp_path/'empty.db');now=time.time();owner=s.create_user('owner@example.com','synthetic-password','Owner')
 monkeypatch.setenv('CLIPBOT_ADMIN_USER_ID',owner)
 a=s.create_user('a@example.com','synthetic-password','A')
 s.set_coverage(a,review_daily=1,user_monthly=100,scouts=1,favorites=1,categories=1,posts=1)
 with s.connection() as db:db.execute('INSERT INTO billing_state(user_id,subscription,customer,plan,status,expires) VALUES(?,?,?,?,?,?)',(a,'sub','cust','creator','active',now-1))
 data=metrics(s,now=now)
 assert data['customersByPlan']==dict(starter=0,creator=0,pro=0,custom=0)
 assert data['customersWithoutActivePlan']==1


def test_missing_owner_configuration_never_counts_unclassified_accounts(tmp_path,monkeypatch):
 monkeypatch.delenv('CLIPBOT_ADMIN_USER_ID',raising=False)
 s=Store(tmp_path/'missing.db');s.create_user('unknown@example.com','synthetic-password','Unknown')
 data=metrics(s)
 assert data['registeredUsers']==0 and data['ownerExclusionConfigured'] is False
