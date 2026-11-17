"""Strict provider upload destinations; no server or credential dependencies."""
import re
from urllib.parse import urlsplit

class PublicationDenied(ValueError):pass

def validate_upload_url(url,platform,remote_id):
    if not isinstance(url,str) or len(url)>8192:raise PublicationDenied('Invalid upload endpoint.')
    p=urlsplit(url)
    if p.scheme!='https' or p.username or p.password or p.port not in (None,443) or p.fragment:raise PublicationDenied('Invalid upload endpoint.')
    if platform=='tiktok':
        valid=p.hostname in {'open-upload.tiktokapis.com','upload.us.tiktokapis.com','upload.eu.tiktokapis.com'} and p.path=='/video/'
    else:
        prefix='video-upload' if platform=='facebook' else 'ig-api-upload'
        valid=p.hostname=='rupload.facebook.com' and bool(re.fullmatch('/'+prefix+r'/(?:v[0-9]{1,2}\.0/)?'+re.escape(remote_id),p.path))
    if not valid:raise PublicationDenied('The provider returned an unsupported upload endpoint.')
    return url

