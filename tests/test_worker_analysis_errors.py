import httpx,pytest
from worker.client import WorkerClient

def test_worker_preserves_safe_analysis_failure_code_without_private_body():
    client=WorkerClient('https://clipbot.example',transport=httpx.MockTransport(lambda request:httpx.Response(409,json={'detail':{'code':'analysis_invalid_json','message':'PRIVATE'}})))
    client.token='a'*32
    with pytest.raises(RuntimeError) as caught:client.request('POST','/api/worker/analyze',{})
    assert caught.value.code=='analysis_invalid_json'
    assert 'PRIVATE' not in str(caught.value)
    client.close()

def test_worker_diagnostic_is_bounded_best_effort_and_drops_unknown_fields():
    captured=[]
    def respond(request):captured.append(request);return httpx.Response(201,json={'ok':True})
    client=WorkerClient('https://clipbot.example',transport=httpx.MockTransport(respond));client.token='a'*32
    assert client.diagnostic({'event':'render_started','jobId':'b'*32,'lease':'c'*32,'stage':'rendering','source':'rendering'})
    assert not client.diagnostic({'event':'render_started','transcript':'PRIVATE'})
    assert len(captured)==1
    client.close()
    assert not client.diagnostic({'event':'render_started'})


@pytest.mark.parametrize('status,expected',[(429,'service_rate_limited'),(422,'analysis_request_invalid'),(409,'analysis_authorization'),(503,'service_unavailable')])
def test_worker_classifies_pre_dispatch_http_failures_without_private_body(status,expected):
    calls=[]
    def respond(request):calls.append(request);return httpx.Response(status,json={'detail':'PRIVATE BODY and TRANSCRIPT'},headers={'Retry-After':'60'})
    client=WorkerClient('https://clipbot.example',transport=httpx.MockTransport(respond));client.token='a'*32
    try:
        with pytest.raises(RuntimeError) as caught:client.request('POST','/api/worker/analyze',{})
        assert caught.value.code==expected
        assert caught.value.http_status==status
        assert 'PRIVATE' not in str(caught.value) and len(calls)==1
    finally:client.close()


def test_configuration_transport_errors_keep_existing_monitor_recovery_behavior():
    def respond(request):raise httpx.ConnectTimeout('PRIVATE URL')
    client=WorkerClient('https://clipbot.example',transport=httpx.MockTransport(respond));client.token='a'*32
    try:
        with pytest.raises(httpx.ConnectTimeout):client.configuration()
        with pytest.raises(RuntimeError) as caught:client.request('POST','/api/worker/analyze',{})
        assert caught.value.code=='service_timeout' and 'PRIVATE' not in str(caught.value)
    finally:client.close()


def test_http_diagnostics_accept_only_bounded_status_metadata():
    calls=[]
    def respond(request):calls.append(request);return httpx.Response(201,json={'ok':True})
    client=WorkerClient('https://clipbot.example',transport=httpx.MockTransport(respond));client.token='a'*32
    base={'event':'worker_request_failed','jobId':'a'*32,'lease':'b'*32,'code':'service_rate_limited'}
    try:
        assert client.diagnostic({**base,'details':{'httpStatus':429}})
        for invalid in ({'httpStatus':'429'},{'httpStatus':True},{'httpStatus':999},{'message':'PRIVATE'}):
            assert not client.diagnostic({**base,'details':invalid})
        assert len(calls)==1 and 'PRIVATE' not in calls[0].content.decode()
    finally:client.close()
