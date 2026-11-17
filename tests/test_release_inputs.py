import hashlib,json
from pathlib import Path
import pytest
from tools.verify_release_inputs import verify_release_inputs


def fixture(root):
    (root/'tools').mkdir();(root/'tools'/'tool.exe').write_bytes(b'approved')
    digest=hashlib.sha256(b'approved').hexdigest()
    return {'schemaVersion':1,'releaseVersion':'0.2.8','sourceComplete':True,'dependencyLockComplete':True,'artifacts':[{'path':'tools/tool.exe','sha256':digest,'sizeBytes':8,'role':'compiler'}]}


def test_pinned_inputs_pass_without_execution(tmp_path):
    assert verify_release_inputs(tmp_path,fixture(tmp_path))==1


@pytest.mark.parametrize('field',['sourceComplete','dependencyLockComplete'])
def test_unfinished_release_evidence_blocks_build(tmp_path,field):
    value=fixture(tmp_path);value[field]=False
    with pytest.raises(ValueError,match='incomplete'):verify_release_inputs(tmp_path,value)


def test_modified_missing_duplicate_and_unsafe_inputs_fail(tmp_path):
    value=fixture(tmp_path)
    (tmp_path/'tools'/'tool.exe').write_bytes(b'malware!')
    with pytest.raises(ValueError):verify_release_inputs(tmp_path,value)
    (tmp_path/'tools'/'tool.exe').unlink()
    with pytest.raises(ValueError):verify_release_inputs(tmp_path,value)
    value['artifacts'][0]['path']='../outside.exe'
    with pytest.raises(ValueError):verify_release_inputs(tmp_path,value)
    value['artifacts'][0]['path']='C:/Windows/tool.exe'
    with pytest.raises(ValueError):verify_release_inputs(tmp_path,value)


def test_duplicate_and_noncanonical_records_fail(tmp_path):
    value=fixture(tmp_path);value['artifacts']*=2
    with pytest.raises(ValueError):verify_release_inputs(tmp_path,value)
    value['artifacts']=value['artifacts'][:1];value['artifacts'][0]['path']='tools/../tools/tool.exe'
    with pytest.raises(ValueError):verify_release_inputs(tmp_path,value)


def test_packaging_inventory_cannot_omit_used_binaries_or_locks(tmp_path):
    from tools.verify_release_inputs import verify_packaging_inputs
    with pytest.raises(ValueError,match='inventory'):verify_packaging_inputs(tmp_path,fixture(tmp_path))


def test_packaging_spec_references_existing_verification_entrypoint():
    import ast,importlib
    spec=Path(__file__).parents[1]/'packaging/companion.spec'
    imports=[node for node in ast.walk(ast.parse(spec.read_text(encoding='utf-8'))) if isinstance(node,ast.ImportFrom) and (node.module or '').startswith('tools.')]
    assert imports
    for node in imports:
        module=importlib.import_module(node.module)
        for value in node.names:assert callable(getattr(module,value.name))


def test_compiler_support_files_and_license_files_must_all_be_pinned(tmp_path):
    from tools.verify_release_inputs import verify_component_coverage
    folder=tmp_path/'packaging/tools/compiler';folder.mkdir(parents=True)
    (folder/'ISCC.exe').write_bytes(b'tool');(folder/'ISCmplr.dll').write_bytes(b'helper')
    manifest={'artifacts':[{'path':'packaging/tools/compiler/ISCC.exe','role':'compiler'}]}
    with pytest.raises(ValueError,match='Unlisted'):verify_component_coverage(tmp_path,manifest)
    manifest['artifacts'].append({'path':'packaging/tools/compiler/ISCmplr.dll','role':'compiler'})
    verify_component_coverage(tmp_path,manifest)
    notices=tmp_path/'packaging/licenses';notices.mkdir();(notices/'LICENSE.txt').write_text('notice')
    with pytest.raises(ValueError,match='Unlisted'):verify_component_coverage(tmp_path,manifest)
    manifest['artifacts'].append({'path':'packaging/licenses/LICENSE.txt','role':'notice'})
    verify_component_coverage(tmp_path,manifest)


def test_build_inventory_includes_bootstrap_and_rejects_extras():
    from tools.verify_release_inputs import verify_build_inventory
    approved={'pip':'26.2.1','fastapi':'0.143.0'}
    verify_build_inventory(approved,approved)
    for value in [{'fastapi':'0.143.0'},{**approved,'pip':'25.0.1'},{**approved,'unreviewed':'1.0'}]:
        with pytest.raises(ValueError):verify_build_inventory(approved,value)


def test_build_runtime_requires_reviewed_windows_python_target():
    from tools.verify_release_inputs import verify_build_runtime
    target={'implementation':'cpython','version':(3,12,14),'platform':'win32','bits':64,'buildPlatform':'win-amd64'}
    verify_build_runtime(target)
    for change in [{'version':(3,12,0)},{'version':(3,13,0)},{'platform':'linux'},{'bits':32},{'implementation':'pypy'}]:
        with pytest.raises(ValueError):verify_build_runtime({**target,**change})


def test_build_runtime_rejects_arm64_even_with_64_bit_windows(monkeypatch):
    import sysconfig
    from tools.verify_release_inputs import verify_build_runtime
    monkeypatch.setattr(sysconfig,'get_platform',lambda:'win-arm64')
    with pytest.raises(ValueError):verify_build_runtime()


def test_repository_notice_files_are_pinned_and_cover_reviewed_packages():
    from tools.verify_release_inputs import verify_component_coverage
    root=Path(__file__).parents[1]
    manifest=json.loads((root/'packaging/release-inputs.json').read_text(encoding='utf-8'))
    verify_component_coverage(root,manifest)
    inventory=json.loads((root/'packaging/package-license-inventory.json').read_text(encoding='utf-8'))
    approved=json.loads((root/'packaging/approved-worker-build.json').read_text(encoding='utf-8'))
    assert inventory['complete'] is True
    assert {r['package'] for r in inventory['records']}==set(approved)
    pinned={r['path']:r for r in manifest['artifacts']}
    for item in inventory['records']:
        assert item['version']==approved[item['package']]
        data=(root/item['path']).read_bytes()
        assert hashlib.sha256(data).hexdigest()==item['sha256']==pinned[item['path']]['sha256']
        assert pinned[item['path']]['role']=='notice'

    assert {p.relative_to(root).as_posix() for p in (root/'packaging/licenses/packages').rglob('*') if p.is_file()}=={r['path'] for r in inventory['records']}
