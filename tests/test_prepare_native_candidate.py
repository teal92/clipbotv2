import importlib
import hashlib
import json
from pathlib import Path

import pytest


def module():
    return importlib.import_module('tools.prepare_native_candidate')


def test_candidate_cannot_create_assets_on_wrong_host(tmp_path):
    with pytest.raises(ValueError,match='matching native'):
        module().prepare('macos-arm64',tmp_path/'runtime',tmp_path/'wheels',
                         tmp_path/'media',tmp_path/'pyav',tmp_path/'assets',host_target='windows-x86_64')
    assert not (tmp_path/'assets').exists()


def test_candidate_lock_keeps_reviewed_versions_and_source_wheel_hash(tmp_path):
    snapshot={'packages':[{'name':'av','version':'18.0.0','artifact':{'kind':'source'}},
        {'name':'httpx','version':'0.28.1','artifact':{'kind':'wheel','sha256':'a'*64}}]}
    approved,lock=module().final_lock(snapshot,{'av':'b'*64})
    assert approved == {'av':'18.0.0','httpx':'0.28.1'}
    assert 'av==18.0.0 --hash=sha256:'+'b'*64 in lock
    with pytest.raises(ValueError):
        module().final_lock(snapshot,{})
    with pytest.raises(ValueError):
        module().final_lock(snapshot,{'av':'not-a-hash'})


def test_linux_source_receipt_requires_exact_wheels_sources_and_success(tmp_path):
    root=tmp_path/'desktop'
    (root/'wheels').mkdir(parents=True)
    (root/'sources').mkdir()
    sources=[]
    receipt={'target':'linux-x86_64','importsPassed':True,'wheels':{},'sources':{}}
    for name in ('pycairo','PyGObject'):
        archive=root/'sources'/(name+'.tar.gz')
        archive.write_bytes(b'pinned source '+name.encode())
        record={'filename':archive.name,'sha256':hashlib.sha256(archive.read_bytes()).hexdigest(),'sizeBytes':archive.stat().st_size}
        sources.append({'name':name,'version':'1.0','artifact':record})
        wheel=root/'wheels'/(name+'-1.0-cp312-cp312-linux_x86_64.whl')
        wheel.write_bytes(b'reviewed wheel '+name.encode())
        receipt['sources'][name]=record
        receipt['wheels'][name]={'version':'1.0','filename':wheel.name,'sha256':hashlib.sha256(wheel.read_bytes()).hexdigest(),'sizeBytes':wheel.stat().st_size}
    path=root/'desktop-diagnostics.json'
    path.write_text(json.dumps(receipt))
    hashes,extra=module().desktop_source_inputs(root,sources)
    assert set(hashes)=={'pycairo','PyGObject'} and len(extra)==2
    receipt['importsPassed']=False
    path.write_text(json.dumps(receipt))
    with pytest.raises(ValueError):module().desktop_source_inputs(root,sources)
    receipt['importsPassed']=True
    receipt['wheels']['pycairo']['filename']='../../outside.whl'
    path.write_text(json.dumps(receipt))
    with pytest.raises(ValueError):module().desktop_source_inputs(root,sources)
    receipt['wheels']['pycairo']['filename']='pycairo-1.0-cp312-cp312-linux_x86_64.whl'
    path.write_text(json.dumps(receipt))
    (root/'sources/pycairo.tar.gz').write_bytes(b'changed source')
    with pytest.raises(ValueError):module().desktop_source_inputs(root,sources)


def test_candidate_input_record_refuses_links_and_empty_files(tmp_path):
    path=tmp_path/'tool'
    path.write_bytes(b'')
    with pytest.raises(ValueError):
        module().input_record(tmp_path,path,'media')
    path.write_bytes(b'verified tool')
    assert module().input_record(tmp_path,path,'media')['sizeBytes']==13
    with pytest.raises(ValueError):
        module().input_record(tmp_path,tmp_path.parent/'outside','source')
    (tmp_path/'nested').mkdir()
    outside=tmp_path.parent/(tmp_path.name+'-outside')
    outside.write_text('must remain outside candidate inputs')
    with pytest.raises(ValueError):
        module().input_record(tmp_path,tmp_path/'nested/../../'/outside.name,'notice')


def test_package_notices_include_british_licence_filename(tmp_path,monkeypatch):
    from types import SimpleNamespace
    license_path=tmp_path/'example.dist-info/LICENCE'
    license_path.parent.mkdir()
    license_path.write_text('Complete reviewed package license text')
    distribution=SimpleNamespace(files=[Path('example.dist-info/LICENCE')],locate_file=lambda p:tmp_path/p)
    monkeypatch.setattr(module().importlib.metadata,'distribution',lambda name:distribution)
    assert 'Complete reviewed package license text' in module().package_notices({'example':'1.0'})


def test_supplemental_notices_require_exact_version_and_unchanged_bytes(tmp_path):
    import hashlib
    path=tmp_path/'packaging/licenses/native/example-LICENSE.txt'
    path.parent.mkdir(parents=True)
    path.write_text('Complete upstream license')
    policy=tmp_path/'packaging/platforms/native-supplemental-notices.json'
    policy.parent.mkdir(parents=True)
    record={'package':'example','version':'1.0','path':path.relative_to(tmp_path).as_posix(),
            'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}
    policy.write_text(json.dumps({'schemaVersion':1,'records':[record]}))
    assert 'Complete upstream license' in module().supplemental_notices('example','1.0',root=tmp_path)
    with pytest.raises(ValueError):
        module().supplemental_notices('example','2.0',root=tmp_path)
    path.write_text('changed')
    with pytest.raises(ValueError):
        module().supplemental_notices('example','1.0',root=tmp_path)
