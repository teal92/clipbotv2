import copy
import importlib
import json
from pathlib import Path

import pytest


def module():
    return importlib.import_module('tools.install_native_wheels')


def evidence(target='macos-arm64'):
    return json.loads(Path(f'packaging/platforms/{target}.dependencies.json').read_text())


def test_committed_dependency_evidence_has_explicit_pending_source_builds():
    wheels, sources = module().validate_snapshot(evidence(), 'macos-arm64')
    assert {item['name'] for item in sources} == {'av'}
    assert wheels and all(item['artifact']['kind'] == 'wheel' for item in wheels)
    _, sources = module().validate_snapshot(evidence('macos-x86_64'), 'macos-x86_64')
    assert {item['name'] for item in sources} == {'av','onnxruntime'}
    _, sources = module().validate_snapshot(evidence('linux-x86_64'), 'linux-x86_64')
    assert {item['name'].lower() for item in sources} == {'av','pygobject','pycairo'}


@pytest.mark.parametrize('change', ['target','runtime','name','version','hash','url','duplicate','closure','release'])
def test_altered_dependency_evidence_is_rejected_before_install(change):
    value = evidence()
    entry = next(item for item in value['packages'] if item['name']=='httpx')
    if change == 'target':
        value['target'] = 'linux-x86_64'
    elif change == 'runtime':
        value['python'] = '3.12.10'
    elif change == 'name':
        entry['name'] = 'httpxx-unreviewed'
    elif change == 'version':
        entry['version'] = '999'
    elif change == 'hash':
        entry['artifact']['sha256'] = 'unverified'
    elif change == 'url':
        entry['artifact']['url'] = 'https://attacker.example/package.whl'
    elif change == 'duplicate':
        value['packages'].append(copy.deepcopy(entry))
    elif change == 'closure':
        value['packages'].remove(entry)
    else:
        value['publicReleaseApproved'] = True
    with pytest.raises(ValueError):
        module().validate_snapshot(value, 'macos-arm64')


def test_wheel_preparation_requires_correct_native_host_without_side_effects(tmp_path):
    with pytest.raises(ValueError, match='matching native'):
        module().prepare('macos-arm64', tmp_path/'out', host_target='windows-x86_64')
    assert not (tmp_path/'out').exists()


def test_failed_install_command_retains_its_diagnostic_output(tmp_path):
    import os
    import subprocess
    import sys
    log = tmp_path/'build.log'
    with pytest.raises(subprocess.CalledProcessError):
        module().run_logged([sys.executable,'-c','print("public build diagnostic");raise SystemExit(1)'],os.environ.copy(),log)
    assert 'public build diagnostic' in log.read_text()
