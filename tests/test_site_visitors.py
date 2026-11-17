import re
import pytest
from server.store import Store

def service(tmp_path):
    from server.site_visitors import SiteVisitors
    return SiteVisitors(Store(tmp_path/'visits.db'))

def test_guests_members_and_separate_pages_count_without_account_identity(tmp_path):
    visits=service(tmp_path);now=1792080000
    assert visits.pulse('a'*32,'203.0.113.1','Browser',now=now)
    assert visits.pulse('b'*32,'203.0.113.1','Browser',now=now)
    assert not visits.pulse('a'*32,'203.0.113.1','Browser',now=now+1)
    assert visits.pulse('a'*32,'203.0.113.1','Browser',now=now+60)
    data=visits.snapshot(now=now+60)
    assert data['activeVisitors']==2 and data['totalVisits']==2
    assert sum(b['visits'] for b in data['history']['day'])==2
    assert visits.snapshot(now=now+400)['activeVisitors']==0
    assert visits.snapshot(now=now+400)['totalVisits']==2

def test_retention_and_aggregate_history_survive_expired_identifiers(tmp_path):
    visits=service(tmp_path);now=1792080000
    visits.pulse('a'*32,'203.0.113.1','Browser',now=now)
    visits.pulse('b'*32,'203.0.113.2','Browser',now=now+2000)
    with visits.store.connection() as db:
        assert db.execute('SELECT COUNT(*) FROM site_visitor_pages').fetchone()[0]==1
        dump=' '.join(str(tuple(r)) for r in db.execute('SELECT * FROM site_visitor_pages'))
        rates=' '.join(str(tuple(r)) for r in db.execute('SELECT * FROM site_visitor_rates'))
    assert 'a'*32 not in dump and '203.0.113.' not in dump+rates
    data=visits.snapshot(now=now+2000)
    assert data['totalVisits']==2 and len(data['history']['day'])==24
    assert len(data['history']['week'])==7 and len(data['history']['month'])==30
    assert len(data['history']['year'])==12 and 1<=len(data['history']['all'])<=32

def test_bots_privacy_requests_invalid_input_and_churn_are_bounded(tmp_path):
    visits=service(tmp_path);now=1792080000
    assert not visits.pulse('a'*32,'203.0.113.1','Googlebot',now=now)
    assert not visits.pulse('a'*32,'203.0.113.1','Browser',now=now,privacy=True)
    for bad in ['x','../a','<script>','a'*10000]:
        with pytest.raises(ValueError):visits.pulse(bad,'203.0.113.1','Browser',now=now)
    results=[visits.pulse(f'{i:032x}','203.0.113.1','Browser',now=now) for i in range(40)]
    assert sum(results)==30 and visits.snapshot(now=now)['totalVisits']==30

def test_launch_timestamp_set_once_and_no_customer_filters(tmp_path,monkeypatch):
    visits=service(tmp_path);now=1792080000
    assert visits.snapshot(now=now)['launchStartedAt'] is None
    monkeypatch.setenv('CLIPBOT_PUBLIC_SIGNUP','1')
    assert visits.snapshot(now=now)['launchStartedAt']==now
    assert visits.snapshot(now=now+100)['launchStartedAt']==now


def test_snapshot_prunes_identifiers_without_losing_aggregate_history(tmp_path):
    visits=service(tmp_path);now=1792080000
    visits.pulse('a'*32,'203.0.113.1','Browser',now=now)
    assert visits.snapshot(now=now+10800)['totalVisits']==1
    with visits.store.connection() as db:
        assert db.execute('SELECT COUNT(*) FROM site_visitor_pages').fetchone()[0]==0
        assert db.execute('SELECT COUNT(*) FROM site_visitor_rates').fetchone()[0]==0


def test_daily_ceiling_blocks_new_pages_but_preserves_existing_heartbeats(tmp_path):
    visits=service(tmp_path);now=1792080000
    visits.pulse('a'*32,'203.0.113.1','Browser',now=now)
    with visits.store.connection(atomic=True) as db:
        db.execute('UPDATE site_visitor_hours SET visits=100000')
    assert not visits.pulse('b'*32,'203.0.113.2','Browser',now=now+60)
    assert visits.pulse('a'*32,'203.0.113.1','Browser',now=now+60)
    assert visits.snapshot(now=now+60)['totalVisits']==100000


def test_all_time_history_stays_bounded_across_many_years(tmp_path):
    from datetime import datetime,timezone
    visits=service(tmp_path)
    with visits.store.connection(atomic=True) as db:
        for year in range(1971,2072):
            db.execute('INSERT INTO site_visitor_hours VALUES(?,?,?)',(datetime(year,1,1,tzinfo=timezone.utc).timestamp(),2,1))
    data=visits.snapshot(now=datetime(2071,12,31,tzinfo=timezone.utc).timestamp())
    assert len(data['history']['all'])<=32
    assert sum(b['visits'] for b in data['history']['all'])==202

def test_anonymous_route_enforces_origin_body_and_privacy(tmp_path,monkeypatch):
    from fastapi.testclient import TestClient
    from server.app import create_app
    monkeypatch.setenv('CLIPBOT_C2_SERVICE_KEY','a'*32)
    app=create_app(Store(tmp_path/'route.db'),origin='https://testserver',local_signup=False)
    with TestClient(app,base_url='https://testserver') as client:
        path='/api/visitor-presence';body={'visitId':'a'*32}
        assert client.post(path,json=body,headers={'Origin':'https://evil.test'}).status_code==403
        assert client.post(path,json={**body,'email':'private@example.test'},headers={'Origin':'https://testserver'}).status_code==422
        assert client.post(path,json=body,headers={'Origin':'https://testserver','DNT':'1'}).status_code==200
        assert client.post(path,json=body,headers={'Origin':'https://testserver'}).json()=={'ok':True}
        assert client.get('/api/operator/metrics').status_code in (401,403)
    assert app.state.site_visitors.snapshot()['totalVisits']==1
