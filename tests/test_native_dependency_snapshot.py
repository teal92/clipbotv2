import importlib

import pytest


def module():
    return importlib.import_module('tools.native_dependency_snapshot')


def record(filename, *, digest='1'*64, url=None):
    return {'filename':filename, 'digests':{'sha256':digest}, 'size':100,
            'url':url or 'https://files.pythonhosted.org/packages/aa/'+filename,
            'yanked':False}


def metadata(files):
    return {'info':{'name':'example','version':'1.0','requires_python':'>=3.9','requires_dist':[]}, 'urls':files}


def test_snapshot_picks_only_the_matching_processor_and_supported_os_floor():
    files = [record('example-1.0-cp312-cp312-macosx_14_0_arm64.whl'),
             record('example-1.0-cp312-cp312-macosx_15_0_arm64.whl'),
             record('example-1.0-cp312-cp312-macosx_11_0_x86_64.whl'),
             record('example-1.0-cp312-cp312-win_amd64.whl')]
    selected = module().select_artifact(metadata(files), 'example', '1.0', 'macos-arm64')
    assert selected['filename'] == files[0]['filename']
    selected = module().select_artifact(metadata(files), 'example', '1.0', 'macos-x86_64')
    assert selected['filename'] == files[2]['filename']
    with pytest.raises(ValueError, match='compatible wheel'):
        module().select_artifact(metadata(files), 'example', '1.0', 'linux-x86_64')


@pytest.mark.parametrize('change', ['name', 'version', 'hash', 'origin', 'yanked', 'python'])
def test_unreviewed_metadata_or_artifact_cannot_enter_snapshot(change):
    value = metadata([record('example-1.0-py3-none-any.whl')])
    if change in {'name','version'}:
        value['info'][change] = 'unexpected'
    elif change == 'hash':
        value['urls'][0]['digests']['sha256'] = 'unverified'
    elif change == 'origin':
        value['urls'][0]['url'] = 'https://attacker.example/example.whl'
    elif change == 'yanked':
        value['urls'][0]['yanked'] = True
    else:
        value['info']['requires_python'] = '>=3.14'
    with pytest.raises(ValueError):
        module().select_artifact(value, 'example', '1.0', 'macos-arm64')


def test_native_source_builds_are_explicit_and_never_replaced_by_vendor_wheels():
    value = metadata([record('example-1.0-py3-none-any.whl'), record('example-1.0.tar.gz')])
    selected = module().select_artifact(value, 'example', '1.0', 'macos-arm64', source=True)
    assert selected['kind'] == 'source'
    assert selected['filename'].endswith('.tar.gz')
    assert selected['nativeBuildAccepted'] is False


def test_source_filename_must_match_the_reviewed_package():
    value = metadata([record('unrelated-1.0.tar.gz')])
    with pytest.raises(ValueError, match='identity'):
        module().select_artifact(value, 'example', '1.0', 'macos-arm64', source=True)


def test_unlisted_or_conflicting_transitive_dependencies_block_lock_completion():
    check = module().validate_dependencies
    versions = {'example':'1.0','six':'1.17.0'}
    assert check(['six>=1.10', 'colorama; sys_platform == "win32"'], versions, 'macos-arm64') == []
    assert check(['mystery-package>=1'], versions, 'macos-arm64')
    assert check(['six>=2'], versions, 'macos-arm64')


def test_snapshot_keeps_only_companion_and_build_dependency_closure():
    packages = [
        {'name':'root','version':'1.0','requires':['six>=1.10']},
        {'name':'six','version':'1.17.0','requires':[]},
        {'name':'server-only','version':'1.0','requires':[],'blocked':'not native'},
    ]
    selected = module().dependency_closure(packages, 'macos-arm64', roots={'root'})
    assert {item['name'] for item in selected} == {'root','six'}


def test_reviewed_source_python_can_bootstrap_with_ensurepips_packaging():
    import subprocess
    import sys
    result = subprocess.run([sys.executable,'-c', '''
import importlib.abc,sys
class NoExternalPackaging(importlib.abc.MetaPathFinder):
    def find_spec(self,fullname,path=None,target=None):
        if fullname=='packaging' or fullname.startswith('packaging.'):
            raise ModuleNotFoundError(fullname,name=fullname)
sys.meta_path.insert(0,NoExternalPackaging())
from tools.native_dependency_snapshot import supported_tags
assert supported_tags('macos-arm64')
'''],capture_output=True,text=True)
    assert result.returncode == 0,result.stderr


def test_repository_packaging_directory_cannot_shadow_bootstrap_parser():
    import subprocess
    import sys
    result = subprocess.run([sys.executable,'-c', '''
import sys,types
from pathlib import Path
namespace=types.ModuleType('packaging')
namespace.__path__=[str(Path.cwd()/'packaging')]
sys.modules['packaging']=namespace
from tools.native_dependency_snapshot import supported_tags
assert supported_tags('macos-arm64')
'''],capture_output=True,text=True)
    assert result.returncode == 0,result.stderr
