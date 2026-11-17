from test_companion import setup
import hashlib,json
from fastapi.testclient import TestClient
from server.app import create_app

def test_website_installer_is_verified_owner_only(setup,monkeypatch):
 store,uid,token,scouts,c=setup;root=store.path.parent/'companion';root.mkdir();blob=b'MZ-test-installer';(root/'ClipBotCompanionSetup.exe').write_bytes(blob)
 (root/'manifest.json').write_text(json.dumps({'version':'0.2.0-beta','sha256':hashlib.sha256(blob).hexdigest(),'sizeBytes':len(blob)}))
 monkeypatch.setenv('CLIPBOT_ADMIN_USER_ID',uid)
 with TestClient(create_app(store,origin='http://testserver')) as client:
  assert client.get('/api/companion/download').status_code==401
  other=store.create_user('other-download@example.com','a-good-long-password','Other');raw,_=store.new_session(other);client.cookies.set('clipbot_session',raw)
  assert client.get('/api/companion/download').status_code==403
  assert client.get('/api/companion/status').json()['download']['available'] is False
  raw,_=store.new_session(uid);client.cookies.set('clipbot_session',raw)
  assert client.get('/api/companion/status').json()['download']['url']=='/api/companion/download'
  result=client.get('/api/companion/download');assert result.content==blob and 'no-store' in result.headers['cache-control']
  (root/'ClipBotCompanionSetup.exe').write_bytes(b'changed');assert client.get('/api/companion/download').status_code==503

def test_installer_rejects_mismatched_hash(tmp_path):
 from server.companion_download import OwnerInstaller
 root=tmp_path/'companion';root.mkdir();(root/'ClipBotCompanionSetup.exe').write_bytes(b'MZ')
 (root/'manifest.json').write_text(json.dumps({'version':'beta','sha256':'0'*64,'sizeBytes':2}))
 assert OwnerInstaller(tmp_path).metadata['available'] is False



import pytest
@pytest.mark.parametrize('manifest',[None,1,[],{}, {'version':3,'sha256':'a'*64,'sizeBytes':2},{'version':'beta','sha256':None,'sizeBytes':2}])
def test_malformed_manifest_fails_closed(tmp_path,manifest):
 from server.companion_download import OwnerInstaller
 root=tmp_path/'companion';root.mkdir();(root/'ClipBotCompanionSetup.exe').write_bytes(b'MZ')
 (root/'manifest.json').write_text(json.dumps(manifest))
 assert OwnerInstaller(tmp_path).metadata['available'] is False

def test_replacement_after_open_streams_verified_original(tmp_path):
 import asyncio
 from server.companion_download import OwnerInstaller
 root=tmp_path/'companion';root.mkdir();path=root/'ClipBotCompanionSetup.exe';blob=b'MZ-original';path.write_bytes(blob)
 (root/'manifest.json').write_text(json.dumps({'version':'beta','sha256':hashlib.sha256(blob).hexdigest(),'sizeBytes':len(blob)}))
 installer=OwnerInstaller(tmp_path);response=installer.response()
 try:path.rename(root/'previous.exe');path.write_bytes(b'MZ-replacement')
 except PermissionError:pass # Windows denies replacement while the verified handle is open.
 async def consume():return b''.join([chunk async for chunk in response.body_iterator])
 assert asyncio.run(consume())==blob
 if path.read_bytes()==blob:path.rename(root/'previous.exe');path.write_bytes(b'MZ-replacement')
 assert installer.ready() is False

