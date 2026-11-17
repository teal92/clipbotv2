import hashlib
import importlib
import json
import io
import urllib.error
from pathlib import Path

import pytest
from fastapi import HTTPException


def module():
    return importlib.import_module('server.companion_remote_download')


def manifest(root,**changes):
    value={'target':'macos-arm64','version':'0.3.0-beta.1','minimumOS':'14.0',
           'sha256':hashlib.sha256(b'reviewed installer').hexdigest(),'sizeBytes':18,
           'assetId':123,'sourceCommit':'a'*40,'channel':'beta','signed':False,
           'provenanceVerified':True,'automatedChecksPassed':True,'publicBetaApproved':True,
           'desktopAcceptancePending':True,'cleanInstallPairedAccepted':False,
           'cleanMachineAccepted':False,'notarized':False}
    value.update(changes)
    folder=root/'companion/targets/macos-arm64'
    folder.mkdir(parents=True,exist_ok=True)
    (folder/'remote-manifest.json').write_text(json.dumps(value))
    return value


def test_native_public_beta_preserves_honest_manual_acceptance_and_no_email_allowlist(tmp_path):
    value=manifest(tmp_path)
    installer=module().RemoteInstaller(tmp_path,'macos-arm64')
    assert installer.ready() and installer.beta_ready and not installer.production_ready
    assert installer.metadata['desktopAcceptancePending'] is True
    assert installer.metadata['url']=='/api/companion/download?target=macos-arm64'
    for key in ('provenanceVerified','automatedChecksPassed','publicBetaApproved','desktopAcceptancePending'):
        manifest(tmp_path,**{key:False})
        assert not module().RemoteInstaller(tmp_path,'macos-arm64').ready()
    manifest(tmp_path,assetId=True)
    assert not module().RemoteInstaller(tmp_path,'macos-arm64').ready()
    manifest(tmp_path,**value)
    assert not module().RemoteInstaller(tmp_path,'windows-x86_64').ready()


def test_asset_metadata_must_match_reviewed_target_version_size_and_digest(tmp_path):
    value=manifest(tmp_path)
    installer=module().RemoteInstaller(tmp_path,'macos-arm64')
    asset={'id':123,'state':'uploaded','name':'ClipBotCompanion-arm64.dmg',
           'size':18,'digest':'sha256:'+value['sha256'],
           'browser_download_url':'https://github.com/YOUR-GITHUB-USERNAME/ClipBotV2-setup-guide/releases/download/companion-0.3.0-beta.1/ClipBotCompanion-arm64.dmg'}
    installer.validate_asset(asset)
    for key,bad in [('id',124),('name','other.dmg'),('size',19),('digest','sha256:'+'b'*64),
                    ('state','new'),('browser_download_url','https://attacker.example/installer')]:
        with pytest.raises(ValueError):installer.validate_asset({**asset,key:bad})


def test_remote_redirect_rejects_unsafe_or_unexpected_hosts_and_expired_links():
    check=module().validate_asset_location
    good='https://release-assets.githubusercontent.com/github-production-release-asset/123/file?se=2099-01-01T00%3A00%3A00Z&sig=private'
    assert check(good,now=0)==good
    for bad in (good.replace('https:','http:'),good.replace('release-assets.githubusercontent.com','evil.example'),
                good.replace('https://','https://user@'),good.replace('2099','2000'),good+'#fragment'):
        with pytest.raises(ValueError):check(bad,now=2_000_000_000)


def test_changed_manifest_disables_remote_download_without_network(tmp_path):
    manifest(tmp_path)
    installer=module().RemoteInstaller(tmp_path,'macos-arm64')
    path=tmp_path/'companion/targets/macos-arm64/remote-manifest.json'
    path.write_text('{}')
    assert not installer.ready()
    with pytest.raises(HTTPException) as error:installer.response()
    assert error.value.status_code==503


def test_delivery_uses_fixed_asset_id_checks_digest_and_caches_bounded_redirect(tmp_path,monkeypatch):
    value=manifest(tmp_path)
    installer=module().RemoteInstaller(tmp_path,'macos-arm64')
    asset={'id':123,'state':'uploaded','name':'ClipBotCompanion-arm64.dmg','size':18,
           'digest':'sha256:'+value['sha256'],
           'browser_download_url':'https://github.com/YOUR-GITHUB-USERNAME/ClipBotV2-setup-guide/releases/download/companion-0.3.0-beta.1/ClipBotCompanion-arm64.dmg'}
    calls=[]
    class Opener:
        def open(self,request,timeout):
            assert request.full_url=='https://api.github.com/repos/YOUR-GITHUB-USERNAME/ClipBotV2-setup-guide/releases/assets/123'
            assert request.get_header('Authorization') is None and timeout==10
            calls.append(request.get_header('Accept'))
            if request.get_header('Accept')=='application/octet-stream':
                raise urllib.error.HTTPError(request.full_url,302,'Found',{'Location':'https://release-assets.githubusercontent.com/github-production-release-asset/123/file?se=2099-01-01T00%3A00%3A00Z&sig=private'},None)
            return io.BytesIO(json.dumps(asset).encode())
    monkeypatch.setattr(module().urllib.request,'build_opener',lambda handler:Opener())
    assert installer.response().status_code==302
    assert installer.response().status_code==302 and len(calls)==2
    installer._cached_until=0
    asset['digest']='sha256:'+'b'*64
    with pytest.raises(HTTPException) as error:installer.response()
    assert error.value.status_code==503 and len(calls)==3


def test_catalog_discovers_only_explicit_native_beta_manifest(tmp_path):
    manifest(tmp_path)
    catalog=importlib.import_module('server.companion_releases').ReleaseCatalog(tmp_path)
    assert catalog.required_version('macos-arm64')=='0.3.0-beta.1'
    assert catalog.required_version('windows-x86_64') is None


def test_native_customer_download_keeps_email_policy_and_beta_acceptance_checks(tmp_path,monkeypatch):
    from fastapi.testclient import TestClient
    from server.app import create_app
    from server.store import Store
    from server.legal import POLICY_VERSION
    value=manifest(tmp_path)
    monkeypatch.setenv('CLIPBOT_COMPANION_PUBLIC_RELEASE','1')
    monkeypatch.setenv('CLIPBOT_COMPANION_UNSIGNED_BETA','1')
    store=Store(tmp_path/'site.db')
    uid=store.create_user('native@example.test','SafePassword!2026','native')
    token,csrf=store.new_session(uid)
    app=create_app(store,origin='http://testserver')
    calls=[]
    def location(self):
        calls.append(True)
        return 'https://release-assets.githubusercontent.com/github-production-release-asset/123/file?se=2099-01-01T00%3A00%3A00Z&sig=private'
    monkeypatch.setattr(module().RemoteInstaller,'_location',location)
    with TestClient(app) as client:
        url='/api/companion/download?target=macos-arm64'
        assert client.get(url,follow_redirects=False).status_code==401
        client.cookies.set('clipbot_session',token)
        assert client.get(url,follow_redirects=False).status_code==428
        app.state.customer_access.accept_policy(uid,POLICY_VERSION)
        with store.connection() as db:db.execute('INSERT INTO email_verification VALUES(?,?)',(uid,1))
        assert client.get(url,follow_redirects=False).status_code==428
        assert calls==[]
        payload={key:value[key] for key in ('target','version','sha256')}
        payload['acknowledged']=True
        assert client.post('/api/companion/beta-accept',json=payload,headers={'Origin':'http://testserver'}).status_code==403
        response=client.post('/api/companion/beta-accept',json=payload,
                             headers={'Origin':'http://testserver','X-CSRF-Token':csrf})
        assert response.status_code==200,response.text
        response=client.get(url,follow_redirects=False)
        assert response.status_code==302
        assert 'no-store' in response.headers['cache-control']
        assert len(calls)==1
