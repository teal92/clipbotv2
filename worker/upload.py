"""One-shot direct provider upload. No redirects, automatic retries or credential logs."""
import hashlib,time
from pathlib import Path
import httpx
from clipbot_common.upload_urls import validate_upload_url,PublicationDenied

class UploadError(ValueError):pass

def upload(path,grant,transport=None):
    clip=Path(path).resolve();artifact=grant['artifact']
    if not clip.is_file() or clip.stat().st_size!=artifact['sizeBytes'] or grant['expiresAt']<=time.time():raise UploadError('Rendered file or upload authorization changed.')
    digest=hashlib.sha256()
    with clip.open('rb') as handle:
        for chunk in iter(lambda:handle.read(1024*1024),b''):digest.update(chunk)
    if digest.hexdigest()!=artifact['sha256']:raise UploadError('Rendered clip no longer matches its approved artifact.')
    try:validate_upload_url(grant['url'],grant['platform'],grant['remoteId'])
    except PublicationDenied:raise UploadError('Unsupported upload endpoint.') from None
    if grant['method'] not in ('POST','PUT'):raise UploadError('Unsupported upload method.')
    headers={**grant['headers'],'Content-Length':str(artifact['sizeBytes'])}
    try:
        with httpx.Client(timeout=httpx.Timeout(120,connect=15),follow_redirects=False,trust_env=False,transport=transport) as client,clip.open('rb') as handle:
            result=client.request(grant['method'],grant['url'],headers=headers,content=iter(lambda:handle.read(1024*1024),b''))
        if result.status_code not in (200,201,202,204):raise UploadError('Upload was not confirmed. Check provider status before retrying.')
        if grant['platform']!='tiktok':
            try:payload=result.json()
            except ValueError:raise UploadError('Upload response requires status reconciliation.') from None
            if not isinstance(payload,dict) or payload.get('success') is not True:raise UploadError('Upload response requires status reconciliation.')
        return {'uploaded':True}
    except httpx.HTTPError:raise UploadError('Upload outcome is unknown. Reconcile status before retrying.') from None
