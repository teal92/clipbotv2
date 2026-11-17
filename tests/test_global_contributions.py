import json
from datetime import datetime,timezone
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from server.store import Store
from server.admin import metrics
from server.customer_admin import build_operator_router

NOW=datetime(2026,10,13,15,tzinfo=timezone.utc).timestamp()
def stamp(text):return datetime.fromisoformat(text).replace(tzinfo=timezone.utc).timestamp()

def test_customer_metrics_exclude_unattributed_shared_feedback(tmp_path,monkeypatch):
 monkeypatch.setenv('CLIPBOT_ADMIN_USER_ID','f'*32)
 s=Store(tmp_path/'metrics.db');a=s.create_user('a@example.com','old-password-long','A');b=s.create_user('b@example.com','old-password-long','B')
 with s.connection() as d:
  for i,created in enumerate(['2026-10-13T01:00','2026-10-13T02:00','2026-10-12T12:00','2026-09-20T12:00','2025-12-01T12:00']):d.execute('INSERT INTO shared_feedback VALUES(?,?,?,?)',(str(i),'approve','["Funny"]',stamp(created)))
  d.execute('INSERT INTO reviews VALUES(?,?,?)',('personal',a,json.dumps({'private':'LOCAL NOTES MUST NOT COUNT AS CONTRIBUTIONS'})))
 data=metrics(s,period='day',now=NOW)
 assert data['scope']=='global' and data['registeredUsers']==2
 c=data['contributions'];assert c['total']==0 and c['excludedUnattributed']==5 and c['target']==1000 and c['timezone']=='UTC' and c['collectionEnabled'] is False
 assert len(c['buckets'])==24 and sum(row['count'] for row in c['buckets'])==0
 assert 'LOCAL NOTES' not in json.dumps(data) and 'a@example.com' not in json.dumps(data)
 assert 'owner/test accounts excluded' in data['source']
 for period,count,total in [('week',7,3),('month',30,4),('year',12,5)]:
  c=metrics(s,period=period,now=NOW)['contributions'];assert len(c['buckets'])==count and sum(row['count'] for row in c['buckets'])==0

def test_zero_contributions_are_not_personal_reviews_or_claimed_learning(tmp_path):
 data=metrics(Store(tmp_path/'zero.db'),period='year',now=NOW)
 assert data['contributions']['total']==0 and len(data['contributions']['buckets'])==12
 assert data['learning']['precision'] is None and not data['contributions']['collectionEnabled']
 assert all(row['count']==0 for row in data['contributions']['buckets'])

def test_private_period_endpoint_is_validated_and_protected(tmp_path):
 app=FastAPI();app.include_router(build_operator_router(Store(tmp_path/'api.db'),None,service_key='x'*40))
 with TestClient(app) as c:
  assert c.get('/api/operator/metrics?period=year').status_code==401
  header={'Authorization':'Bearer '+'x'*40}
  assert c.get('/api/operator/metrics?period=year',headers=header).json()['contributions']['period']=='year'
  assert c.get('/api/operator/metrics?period=decade',headers=header).status_code==422

def test_all_time_includes_old_records_in_bounded_buckets(tmp_path):
 from server.admin import contribution_series
 s=Store(tmp_path/'all.db')
 with s.connection() as db:
  for i,when in enumerate(['1971-01-01T00:00','2020-03-01T12:00','2026-10-13T12:00','2027-01-01T00:00']):
   db.execute('INSERT INTO shared_feedback VALUES(?,?,?,?)',(str(i),'approve','[]',stamp(when)))
  result=contribution_series(db,'all',NOW)
 assert result['total']==3 and sum(b['count'] for b in result['buckets'])==3
 assert len(result['buckets'])<=32 and result['buckets'][0]['key'].startswith('1971')
 assert 'all' in result['supportedPeriods']
