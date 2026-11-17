from server.telemetry import Telemetry

def test_telemetry_is_bounded_and_aggregate_without_paths_or_identity():
    metrics=Telemetry(capacity=10)
    for i in range(30):metrics.record(10+i,500 if i==29 else 200)
    result=metrics.snapshot()
    assert result['sampleCount']==10 and result['errorsLastMinute']==1
    assert result['p95LatencyMs']>=result['medianLatencyMs']>=0
    assert 'user' not in str(result).lower() and 'path' not in str(result).lower()
