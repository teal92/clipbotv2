from pathlib import Path
from fastapi.testclient import TestClient
import pytest
from worker.local_app import create_local_app

def test_local_worker_pairing_requires_exact_host_origin_and_csrf(tmp_path):
    app=create_local_app('https://clipbot.example',tmp_path,start_runtime=False)
    with TestClient(app,base_url='http://127.0.0.1:8767',client=('127.0.0.1',32100)) as client:
        assert client.get('/').status_code==200
        assert client.get('/',headers={'Host':'evil.test:8767'}).status_code==403
        assert client.post('/pair',json={'code':'x'*24},headers={'Origin':'https://evil.test'}).status_code==403
        assert client.post('/pair',json={'code':'x'*24},headers={'Origin':'http://127.0.0.1:8767'}).status_code==403
        assert client.get('/media/../secret').status_code in (404,403)
        assert client.get('/status').json()['paired'] is False

def test_local_preview_exposes_only_registered_scoped_artifact(tmp_path):
    app=create_local_app('https://clipbot.example',tmp_path,start_runtime=False)
    job=tmp_path/('a'*32);job.mkdir();clip=job/'clip.mp4';clip.write_bytes(b'clip')
    token='b'*64;app.state.previews[token]=clip
    with TestClient(app,base_url='http://127.0.0.1:8767',client=('127.0.0.1',32100)) as client:
        assert client.get('/media/'+token).status_code==200
        assert client.get('/media/'+'c'*64).status_code==404
        assert client.get('/preview/'+token).status_code==200
        app.state.previews.clear()
        assert client.get('/media/'+token).status_code==404


def test_chunked_pair_body_is_bounded_before_parsing(tmp_path):
    import re,json
    app=create_local_app('https://clipbot.example',tmp_path,start_runtime=False)
    with TestClient(app,base_url='http://127.0.0.1:8767',client=('127.0.0.1',32100)) as client:
        csrf=re.search("name=csrf content='([a-f0-9]+)'",client.get('/').text).group(1)
        body=json.dumps({'code':'x'*24,'extra':'z'*3000}).encode()
        response=client.post('/pair',content=iter([body[:1000],body[1000:]]),headers={'Origin':'http://127.0.0.1:8767','X-CSRF-Token':csrf,'Content-Type':'application/json'})
        assert response.status_code==413

def test_windows_device_storage_is_user_encrypted_and_origin_bound(tmp_path):
    import os
    if os.name!='nt':pytest.skip('Windows DPAPI integration')
    from worker.credentials import save,load
    path=tmp_path/'device.bin';token='PRIVATE-DEVICE-TOKEN-LONG-ENOUGH'
    save(path,'https://clipbot.example',token)
    assert token.encode() not in path.read_bytes()
    assert load(path,'https://clipbot.example')==token
    assert load(path,'https://other.example') is None
