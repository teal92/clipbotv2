import importlib
import json
import subprocess
import sys
from pathlib import Path

import pytest
import yaml


def test_native_probe_wrong_host_never_claims_acceptance(tmp_path):
    target='linux-x86_64' if sys.platform=='darwin' else 'macos-arm64'
    result = subprocess.run([sys.executable, 'tools/probe_native_companion.py', '--target', target, '--output', str(tmp_path/'receipt.json')], capture_output=True, text=True)
    assert result.returncode != 0
    receipt = json.loads((tmp_path/'receipt.json').read_text())
    assert receipt['passed'] is False
    assert receipt['cleanMachineAccepted'] is False


def test_native_build_workflow_cannot_auto_run_or_write_repository():
    path = Path('.github/workflows/companion-native.yml')
    # BaseLoader keeps YAML's literal "on" key instead of interpreting it as True.
    value = yaml.load(path.read_text(), Loader=yaml.BaseLoader)
    assert set(value['on']) == {'workflow_dispatch'}
    assert value['permissions'] == {'contents':'read'}
    for job in value['jobs'].values():
        assert int(job['timeout-minutes']) <= 45
        for step in job['steps']:
            if 'uses' in step:
                action, commit = step['uses'].rsplit('@',1)
                assert action.startswith('actions/')
                assert len(commit) == 40 and all(char in '0123456789abcdef' for char in commit)
            assert '${{ secrets.' not in json.dumps(step)
            if 'run' in step:
                assert '${{ inputs.' not in step['run']


def test_native_probe_accepts_only_full_commit_hash():
    module = importlib.import_module('tools.probe_native_companion')
    assert module.validated_commit('a'*40) == 'a'*40
    for value in ['main', 'abc', '$(touch malicious)', 'a'*40+'\n']:
        with pytest.raises(ValueError):
            module.validated_commit(value)


def test_runtime_compilation_is_separate_from_package_release():
    value = yaml.load(Path('.github/workflows/companion-native.yml').read_text(), Loader=yaml.BaseLoader)
    assert 'runtime' in value['on']['workflow_dispatch']['inputs']['mode']['options']
    steps = value['jobs']['native']['steps']
    runtime = next(step for step in steps if 'build_native_runtime.py' in step.get('run', ''))
    assert runtime['if'] == "inputs.mode == 'runtime' || inputs.mode == 'wheels' || inputs.mode == 'decoder' || inputs.mode == 'build' || inputs.mode == 'onnx' || inputs.mode == 'desktop'"
    setup = next(step for step in steps if step.get('uses', '').startswith('actions/setup-python@'))
    assert "inputs.mode == 'probe'" in setup['if']
    assert not any('release' in step.get('uses', '') for step in steps)


def test_linux_runtime_build_has_required_compression_headers():
    value = yaml.load(Path('.github/workflows/companion-native.yml').read_text(), Loader=yaml.BaseLoader)
    steps = value['jobs']['native']['steps']
    prerequisite = next((step for step in steps if 'libbz2-dev' in step.get('run', '')), None)
    assert prerequisite is not None, 'Linux source Python requires bzip2 development headers'
    assert prerequisite['if'] == "runner.os == 'Linux' && (inputs.mode == 'runtime' || inputs.mode == 'wheels' || inputs.mode == 'decoder' || inputs.mode == 'build' || inputs.mode == 'desktop')"
    for package in ['libbz2-dev','liblzma-dev','libsqlite3-dev','zlib1g-dev']:
        assert package in prerequisite['run']
    assert '--no-install-recommends' in prerequisite['run']


def test_media_compilation_has_no_customer_artifact_publication():
    value = yaml.load(Path('.github/workflows/companion-native.yml').read_text(), Loader=yaml.BaseLoader)
    assert 'media' in value['on']['workflow_dispatch']['inputs']['mode']['options']
    steps = value['jobs']['native']['steps']
    media = next(step for step in steps if 'build_native_media.py' in step.get('run', ''))
    assert media['if'] == "inputs.mode == 'media' || inputs.mode == 'decoder' || inputs.mode == 'build'"
    upload = next(step for step in steps if step.get('with', {}).get('name','').startswith('native-media-'))
    assert upload['with']['retention-days'] == '1'
    assert 'installed' not in upload['with']['path']
    assert 'downloads' not in upload['with']['path']


def test_wheel_check_uses_only_the_reviewed_source_runtime():
    value = yaml.load(Path('.github/workflows/companion-native.yml').read_text(), Loader=yaml.BaseLoader)
    assert 'wheels' in value['on']['workflow_dispatch']['inputs']['mode']['options']
    steps = value['jobs']['native']['steps']
    install = next(step for step in steps if 'install_native_wheels.py' in step.get('run', ''))
    assert install['if'] == "inputs.mode == 'wheels' || inputs.mode == 'decoder' || inputs.mode == 'build' || inputs.mode == 'onnx' || inputs.mode == 'desktop'"
    assert 'native-runtime/runtime/bin/python3.12' in install['run']


def test_decoder_check_uses_isolated_environment_and_only_exports_internal_wheel():
    value = yaml.load(Path('.github/workflows/companion-native.yml').read_text(), Loader=yaml.BaseLoader)
    assert 'decoder' in value['on']['workflow_dispatch']['inputs']['mode']['options']
    steps = value['jobs']['native']['steps']
    build = next(step for step in steps if 'build_native_pyav.py' in step.get('run', ''))
    assert build['if'] == "inputs.mode == 'decoder' || inputs.mode == 'build'"
    assert 'native-wheels/environment/bin/python' in build['run']
    assert '--media-root "$RUNNER_TEMP/native-media"' in build['run']
    upload = next(step for step in steps if step.get('with',{}).get('name','').startswith('native-decoder-'))
    assert upload['with']['retention-days'] == '1'
    assert '*.whl' in upload['with']['path']


def test_candidate_assembly_precedes_packaging_and_stays_internal():
    value=yaml.load(Path('.github/workflows/companion-native.yml').read_text(),Loader=yaml.BaseLoader)
    steps=value['jobs']['native']['steps']
    assembly=next((i for i,s in enumerate(steps) if 'prepare_native_candidate.py' in s.get('run','')),None)
    packaging=next(i for i,s in enumerate(steps) if 'packaging/build-native.py' in s.get('run',''))
    assert assembly is not None and assembly < packaging
    assert 'native-wheels/environment/bin/python' in steps[packaging]['run']
    assert '--inputs-root' in steps[packaging]['run']
    upload=next(s for s in steps if s.get('with',{}).get('name','').startswith('internal-native-candidate-'))
    assert upload['with']['retention-days']=='1'
    assert 'work/' not in upload['with']['path']


def test_packaged_checks_run_before_internal_installer_retention():
    value=yaml.load(Path('.github/workflows/companion-native.yml').read_text(),Loader=yaml.BaseLoader)
    steps=value['jobs']['native']['steps']
    check=next((i for i,s in enumerate(steps) if 'tools/accept_native_companion.py' in s.get('run','')),None)
    upload=next(i for i,s in enumerate(steps) if s.get('with',{}).get('name','').startswith('internal-native-candidate-'))
    assert check is not None and check < upload
    assert steps[check]['if']=="inputs.mode == 'build'"
    assert 'native-wheels/environment/bin/python' in steps[check]['run']


def test_intel_onnx_check_is_a_separate_native_library_check():
    value=yaml.load(Path('.github/workflows/companion-native.yml').read_text(),Loader=yaml.BaseLoader)
    assert 'onnx' in value['on']['workflow_dispatch']['inputs']['mode']['options']
    steps=value['jobs']['native']['steps']
    build=next(s for s in steps if 'tools/build_native_onnx.py' in s.get('run',''))
    assert build['if']=="inputs.mode == 'onnx'"
    assert 'native-wheels/environment/bin/python' in build['run']
    validate=next(s for s in steps if s.get('name')=='Validate source selector')
    assert 'macos-x86_64' in validate['run']
    upload=next(s for s in steps if s.get('with',{}).get('name','').startswith('native-onnx-'))
    assert upload['with']['retention-days']=='1'
    assert '*.whl' in upload['with']['path']
    assert '.dmg' not in upload['with']['path']


def test_linux_desktop_check_requires_distro_headers_and_no_installer_release():
    value=yaml.load(Path('.github/workflows/companion-native.yml').read_text(),Loader=yaml.BaseLoader)
    assert 'desktop' in value['on']['workflow_dispatch']['inputs']['mode']['options']
    steps=value['jobs']['native']['steps']
    prerequisites=next(s for s in steps if s.get('name')=='Install Linux desktop build prerequisites')
    assert prerequisites['if']=="runner.os == 'Linux' && (inputs.mode == 'desktop' || inputs.mode == 'build')"
    assert 'libglib2.0-dev' in prerequisites['run'] and 'libcairo2-dev' in prerequisites['run']
    assert 'libgirepository-2.0-dev' in prerequisites['run']
    assert 'pkg-config --atleast-version=2.80 girepository-2.0' in prerequisites['run']
    build=next(s for s in steps if 'tools/build_native_linux_desktop.py' in s.get('run',''))
    assert build['if']=="runner.os == 'Linux' && (inputs.mode == 'desktop' || inputs.mode == 'build')"
    assert 'native-wheels/environment/bin/python' in build['run']
    upload=next(s for s in steps if s.get('with',{}).get('name','').startswith('native-desktop-'))
    assert upload['with']['retention-days']=='1' and '.deb' not in upload['with']['path']
    assembly=next(s for s in steps if 'prepare_native_candidate.py' in s.get('run',''))
    assert '--desktop-root' in assembly['run']
