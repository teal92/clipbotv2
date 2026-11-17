"""Public native beta assets, pinned to the owner's existing release repository.

No request-provided URL or service credential is used. Account/policy/consent
checks remain in companion_api before any external download is issued.
"""
from datetime import datetime
import json
import os
from pathlib import Path
import re
import threading
import time
from urllib.parse import parse_qs, urlsplit
import urllib.error
import urllib.request

from fastapi import HTTPException
from fastapi.responses import RedirectResponse

from .companion_download import FILENAMES, OwnerInstaller

REPOSITORY = 'YOUR-GITHUB-USERNAME/ClipBotV2-setup-guide'


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def validate_asset_location(location, *, now=None):
    if not isinstance(location, str) or len(location) > 8192 or any(ord(c) < 33 for c in location):
        raise ValueError('Invalid release asset location.')
    parsed = urlsplit(location)
    if (parsed.scheme != 'https' or parsed.hostname != 'release-assets.githubusercontent.com'
            or parsed.port not in (None, 443) or parsed.username or parsed.password or parsed.fragment
            or not parsed.path.startswith('/github-production-release-asset/')):
        raise ValueError('Unapproved release asset location.')
    expiry = parse_qs(parsed.query).get('se', [])
    if len(expiry) != 1:
        raise ValueError('Missing release asset expiry.')
    expires = datetime.fromisoformat(expiry[0].replace('Z', '+00:00'))
    if expires.tzinfo is None or expires.timestamp() <= (time.time() if now is None else now) + 180:
        raise ValueError('Release asset location expires too soon.')
    return location


class RemoteInstaller:
    def __init__(self, root, target):
        self.target = target
        self.metadata = {'available': False}
        self.production_ready = self.beta_ready = False
        self.signature = None
        self._lock = threading.Lock()
        self._cached = None
        self._cached_until = 0
        self.path = Path(root) / 'companion/targets' / target / 'remote-manifest.json'
        if target not in FILENAMES or target == 'windows-x86_64':
            return
        try:
            if any(p.is_symlink() or (hasattr(p, 'is_junction') and p.is_junction()) for p in (self.path, *self.path.parents)):
                return
            with self.path.open('rb') as stream:
                before = OwnerInstaller.identity(os.fstat(stream.fileno()))
                data = stream.read(100_001)
                after = OwnerInstaller.identity(os.fstat(stream.fileno()))
            if before != after or len(data) > 100_000:
                return
            value = json.loads(data)
            if (value.get('target') != target or value.get('channel') != 'beta'
                    or value.get('signed') is not False or value.get('notarized') is not False
                    or any(value.get(k) is not True for k in ('provenanceVerified', 'automatedChecksPassed',
                                                            'publicBetaApproved', 'desktopAcceptancePending'))
                    or any(value.get(k) is not False for k in ('cleanInstallPairedAccepted', 'cleanMachineAccepted'))
                    or type(value.get('assetId')) is not int or value['assetId'] <= 0
                    or type(value.get('sizeBytes')) is not int or not 0 < value['sizeBytes'] < 2**31
                    or not re.fullmatch(r'[a-f0-9]{64}', value.get('sha256', ''))
                    or not re.fullmatch(r'[a-f0-9]{40}', value.get('sourceCommit', ''))
                    or not re.fullmatch(r'[0-9]+\.[0-9]+\.[0-9]+-beta\.[0-9]+', value.get('version', ''))
                    or not re.fullmatch(r'[A-Za-z0-9 .+_-]{1,80}', value.get('minimumOS', ''))):
                return
            self.asset = value
            self.signature = after
            self.beta_ready = True
            self.metadata = {key: value[key] for key in ('target', 'version', 'minimumOS', 'sha256', 'signed', 'desktopAcceptancePending')}
            self.metadata.update(available=True, url='/api/companion/download?target=' + target)
        except (OSError, ValueError, KeyError, TypeError, AttributeError):
            pass

    def ready(self):
        try:
            return self.signature is not None and self.signature == OwnerInstaller.identity(self.path.stat())
        except OSError:
            return False

    def validate_asset(self, value):
        filename = FILENAMES[self.target]
        expected_url = f'https://github.com/{REPOSITORY}/releases/download/companion-{self.asset["version"]}/{filename}'
        if (not isinstance(value, dict) or value.get('id') != self.asset['assetId'] or value.get('state') != 'uploaded'
                or value.get('name') != filename or value.get('size') != self.asset['sizeBytes']
                or value.get('digest') != 'sha256:' + self.asset['sha256']
                or value.get('browser_download_url') != expected_url):
            raise ValueError('Release asset differs from reviewed installer.')

    def _location(self):
        endpoint = f'https://api.github.com/repos/{REPOSITORY}/releases/assets/{self.asset["assetId"]}'
        opener = urllib.request.build_opener(NoRedirect)
        headers = {'User-Agent': 'ClipBot-release-download', 'Accept': 'application/vnd.github+json',
                   'X-GitHub-Api-Version': '2022-11-28'}
        with opener.open(urllib.request.Request(endpoint, headers=headers), timeout=10) as response:
            data = response.read(100_001)
        if len(data) > 100_000:
            raise ValueError('Release asset metadata exceeds limit.')
        self.validate_asset(json.loads(data))
        headers['Accept'] = 'application/octet-stream'
        try:
            with opener.open(urllib.request.Request(endpoint, headers=headers), timeout=10):
                raise ValueError('Release asset did not provide a fixed-ID redirect.')
        except urllib.error.HTTPError as error:
            if error.code != 302:
                raise ValueError('Release asset download unavailable.') from None
            return validate_asset_location(error.headers.get('Location'))

    def response(self):
        if not self.ready():
            raise HTTPException(503, 'Companion download is being prepared. Try again shortly.')
        try:
            with self._lock:
                if not self._cached or self._cached_until <= time.monotonic():
                    self._cached = self._location()
                    self._cached_until = time.monotonic() + 120
                location = validate_asset_location(self._cached)
        except (OSError, ValueError, TypeError, KeyError):
            raise HTTPException(503, 'Companion download is temporarily unavailable. Try again shortly.') from None
        return RedirectResponse(location, status_code=302, headers={
            'Cache-Control': 'private, no-store', 'Referrer-Policy': 'no-referrer',
            'X-Content-Type-Options': 'nosniff'})
