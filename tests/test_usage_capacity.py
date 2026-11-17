from datetime import datetime,timezone
import json
from fastapi.testclient import TestClient
from server.store import Store
from server.app import create_app


def test_private_usage_totals_and_top_three_per_tier_exclude_owner(tmp_path,monkeypatch):
    from server.usage_capacity import capacity_usage
    from server.budgets import BudgetLedger
    store=Store(tmp_path/'usage.db');now=datetime(2026,10,15,12,tzinfo=timezone.utc).timestamp()
    owner=store.create_user('owner@example.test','SafePassword!2026','Owner');monkeypatch.setenv('CLIPBOT_ADMIN_USER_ID',owner)
    def seed(uid,spend,reserved=0,day='2026-10-15'):
        with store.connection() as db:
            db.execute('INSERT INTO jobs VALUES(?,?,?,?,?,?,?,?,?)',(uid,'job-'+day,day,day[:7],reserved,spend,10,20,'reserved' if reserved else 'settled'))
            db.execute('INSERT INTO job_timestamps VALUES(?,?,?)',(uid,'job-'+day,datetime.fromisoformat(day).replace(tzinfo=timezone.utc).timestamp()))
    seed(owner,500)
    for plan in ('starter','creator','pro','custom'):
        for n in range(4):
            uid=store.create_user(f'{plan}{n}@example.test','SafePassword!2026',f'{plan}{n}')
            store.set_coverage(uid,review_daily=30,user_monthly=2000000,scouts=6,favorites=0,categories=0,posts=20)
            with store.connection() as db:
                db.execute('INSERT INTO billing_state VALUES(?,?,?,?,?,?,?,?)',(uid,'sub_'+uid,'cus_'+uid,plan,'active',now+86400,900,'request'))
                db.execute('INSERT INTO billing_periods VALUES(?,?,?,?)',(uid,'sub_'+uid,now-20*86400,now+86400))
            seed(uid,100*(n+1),10)
            if n==3:seed(uid,1000,day='2026-09-30')
    result=capacity_usage(store,BudgetLedger(store),now)
    assert result['daily']['spentMicros']==4500 and result['daily']['reservedMicros']==160
    assert result['monthly']['spentMicros']==4500
    for plan,rows in result['topUsers'].items():
        assert len(rows)==3 and rows[0]['name']==plan+'3'
        assert rows[0]['monthlySpentMicros']==1400 and rows[0]['dailySpentMicros']==400
        assert rows[0]['periodStart']<datetime(2026,10,1,tzinfo=timezone.utc).timestamp()
        assert owner not in {r['id'] for r in rows}
    monkeypatch.delenv('CLIPBOT_ADMIN_USER_ID')
    assert all(rows==[] for rows in capacity_usage(store,BudgetLedger(store),now)['topUsers'].values())


def test_usage_metadata_is_operator_only_and_has_no_customer_email_or_credentials(tmp_path,monkeypatch):
    monkeypatch.setenv('CLIPBOT_C2_SERVICE_KEY','k'*40)
    app=create_app(Store(tmp_path/'api.db'),origin='http://testserver')
    with TestClient(app) as client:
        assert client.get('/api/operator/metrics').status_code==401
        response=client.get('/api/operator/metrics',headers={'Authorization':'Bearer '+'k'*40})
        assert response.status_code==200
        data=response.json();assert data['capacityUsage']['daily']['limitMicros']==20000000
        assert data['planningPolicy']['proposedPlans']['starter']['dailyReviews']==30
        for key in ('password','api_key','access_token','email'):assert key not in json.dumps(data['capacityUsage']).lower()
