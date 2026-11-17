import json,pytest
from server.store import Store
from server.pipeline_events import EventStore

def test_events_are_owner_scoped_bounded_and_template_only(tmp_path,capsys):
    store=Store(tmp_path/'events.db');events=EventStore(store)
    for i in range(505):events.record('owner','job_reported',job_id='a'*32,stage='capturing',elapsed_ms=i)
    events.record('other','job_cancelled',job_id='b'*32,stage='cancelled')
    rows=events.snapshot('owner',limit=500)
    assert len(rows)==500 and all(row['stage']=='capturing' for row in rows)
    assert events.snapshot('owner',cursor=rows[-1]['id'])==[]
    assert len(events.snapshot('other'))==1
    with pytest.raises(ValueError):events.record('owner','PRIVATE SECRET')
    with pytest.raises(ValueError):events.record('owner','job_reported',code='PRIVATE SECRET')
    assert 'PRIVATE' not in json.dumps(events.snapshot('owner',limit=500))

def test_event_storage_excludes_unknown_payload_fields(tmp_path):
    events=EventStore(Store(tmp_path/'events.db'))
    with pytest.raises(TypeError):events.record('owner','job_reported',transcript='private')
    with pytest.raises(ValueError):events.record('owner','job_reported',login='https://user:secret@host')
    with pytest.raises(ValueError):events.record('owner','job_reported',elapsed_ms=float('nan'))

def test_newest_page_and_iso_timestamp_are_logs_compatible(tmp_path):
    from datetime import datetime
    events=EventStore(Store(tmp_path/'events.db'))
    for i in range(5):events.record('owner','job_reported',job_id=str(i),stage='capturing',level='warn',source='worker')
    latest=events.snapshot('owner',limit=2)
    assert [row['jobId'] for row in latest]==['3','4']
    assert latest[0]['level']=='warning' and latest[0]['source']=='service'
    assert datetime.fromisoformat(latest[0]['createdAt']).tzinfo is not None
    assert [row['jobId'] for row in events.snapshot('owner',cursor=latest[0]['id'])]==['4']


def test_selection_outcomes_are_not_technical_failures(tmp_path):
 events=EventStore(Store(tmp_path/'outcomes.db'))
 for code in ('analysis_no_moment','analysis_below_threshold','analysis_length_settings'):
  event=events.record('owner','analysis_rejected',job_id='one',stage='analyzing',code=code,level='info')
  assert event['code']==code and event['level']=='info'
