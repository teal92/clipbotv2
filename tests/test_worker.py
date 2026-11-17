import httpx,pytest
from worker.client import WorkerClient,service_origin

def test_remote_connections_require_https():
    assert service_origin('http://127.0.0.1:8766/')=='http://127.0.0.1:8766'
    assert service_origin('https://clipbot.example.com')=='https://clipbot.example.com'
    for address in ['http://example.com','https://user:secret@example.com','https://example.com/?token=secret','file:///tmp/x']:
        with pytest.raises(ValueError):service_origin(address)

def test_pairing_token_is_scoped_and_cleared_on_revocation():
    requests=[]
    def handler(request):
        requests.append(request)
        if request.url.path.endswith('/connect'):return httpx.Response(201,json={'token':'test-token-value-long-enough'})
        return httpx.Response(401,json={})
    client=WorkerClient('https://clipbot.example.com',httpx.MockTransport(handler))
    client.connect('one-time-code-for-test')
    with pytest.raises(RuntimeError):client.heartbeat()
    assert requests[0].headers.get('authorization') is None
    assert requests[1].headers['authorization']=='Bearer test-token-value-long-enough'
    assert client.token is None
    client.close()
