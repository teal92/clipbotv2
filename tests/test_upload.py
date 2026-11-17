import hashlib,time
import httpx,pytest
from worker.upload import upload,UploadError

def test_upload_verifies_artifact_and_never_follows_redirect(tmp_path):
    clip=tmp_path/'clip.mp4';clip.write_bytes(b'clip')
    grant={'platform':'facebook','remoteId':'123','url':'https://rupload.facebook.com/video-upload/v24.0/123','method':'POST','headers':{'Authorization':'OAuth SECRET'},'artifact':{'sha256':hashlib.sha256(b'clip').hexdigest(),'sizeBytes':4},'expiresAt':time.time()+60}
    calls=[]
    def handler(request):calls.append(request);return httpx.Response(302,headers={'Location':'https://evil.test'})
    with pytest.raises(UploadError):upload(clip,grant,transport=httpx.MockTransport(handler))
    assert len(calls)==1
    clip.write_bytes(b'changed')
    with pytest.raises(UploadError):upload(clip,grant,transport=httpx.MockTransport(handler))
    assert len(calls)==1
def test_companion_upload_does_not_import_server_auth_or_billing():
    import subprocess
    import sys
    result = subprocess.run([sys.executable, '-c',
        'import worker.upload,sys; assert not any(n=="server" or n.startswith("server.") for n in sys.modules), "Companion imports server services"'], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
