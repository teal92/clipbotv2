"""Build PyAV against the controlled native decoder, without vendor libraries."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0,str(ROOT))
from tools.native_dependency_snapshot import TARGETS, canonicalize_name, parse_wheel_filename, supported_tags
from tools.verify_native_release_inputs import verify_native_runtime, verify_native_pyav
from tools.build_native_media import BASELINE, profile_name
from tools.install_native_wheels import run_logged
from worker.platforms.identity import current_target

PYAV_COMMIT = '54a4395bb4cdd9cdd53ff6216c50b69f6475c13d'


def native_link_flags(target):
    if target not in TARGETS:
        raise ValueError('Unsupported native decoder target.')
    # Wheel repair lengthens dylib paths. Reserve Mach-O load-command space at
    # link time so install_name_tool can relocate them without rebuilding.
    return '-Wl,-headerpad_max_install_names' if target.startswith('macos-') else ''


def validate_wheel_name(path, target):
    name,version,_,tags = parse_wheel_filename(Path(path).name)
    if canonicalize_name(name) != 'av' or str(version) != '18.0.0' or not tags.intersection(supported_tags(target)):
        raise ValueError('Repaired decoder wheel has the wrong identity, version, architecture or OS floor.')


def decoder_prefix(media_root, receipt, target):
    if (target not in TARGETS or receipt.get('target') != target or receipt.get('registryCommit') != BASELINE
            or receipt.get('mediaFeatureChecksPassed') is not True):
        raise ValueError('Checked native media receipt is required.')
    root = Path(media_root).resolve()
    name = profile_name(target,'decoder')
    expected = root/'installed/decoder'/name
    record = receipt.get('profiles',{}).get('decoder',{})
    if record.get('triplet') != name or Path(record.get('installed','')).absolute() != expected:
        raise ValueError('Native decoder prefix differs from the checked build directory.')
    if expected.is_symlink() or not expected.is_dir():
        raise ValueError('Unsafe or missing native decoder prefix.')
    files = receipt.get('files',{})
    scope = expected.relative_to(root).as_posix()+'/'
    if not isinstance(files,dict) or not any(key.startswith(scope+'lib/libavcodec') for key in files):
        raise ValueError('Reviewed native decoder file hashes are required.')
    total = 0
    for path in expected.rglob('*'):
        resolved = path.resolve()
        if not resolved.is_relative_to(expected):
            raise ValueError('Native decoder link escapes its checked prefix.')
        if not path.is_file():
            continue
        entry = files.get(resolved.relative_to(root).as_posix())
        total += path.stat().st_size
        if total > 300_000_000 or not entry or entry.get('sizeBytes') != path.stat().st_size:
            raise ValueError('Native decoder file differs from its checked receipt.')
        with path.open('rb') as stream:
            if hashlib.file_digest(stream,'sha256').hexdigest() != entry.get('sha256'):
                raise ValueError('Native decoder file hash differs from its checked receipt.')
    return expected


def build(target, media_root, output, *, host_target=None):
    if target not in TARGETS or (host_target or current_target()) != target:
        raise ValueError('Decoder compilation requires a matching native host and processor.')
    verify_native_runtime()
    media_root = Path(media_root).resolve()
    path = media_root/'media-diagnostics.json'
    if path.stat().st_size > 1_000_000:
        raise ValueError('Native decoder receipt exceeds limits.')
    prefix = decoder_prefix(media_root,json.loads(path.read_text()),target)
    output = Path(output).absolute()
    if output.exists():
        raise ValueError('Use a new native decoder output directory.')
    output.mkdir(mode=0o700,parents=True)
    output = output.resolve()
    log = output/'build.log'
    source = output/'source'
    environment = {key:value for key,value in os.environ.items() if key not in {
        'PYTHONPATH','PYTHONHOME','CPATH','LIBRARY_PATH','CMAKE_PREFIX_PATH','PKG_CONFIG_PATH',
        'PKG_CONFIG_LIBDIR','CFLAGS','CXXFLAGS','CPPFLAGS','LDFLAGS','DYLD_LIBRARY_PATH','LD_LIBRARY_PATH'}
        and not key.startswith(('CLIPBOT_','ANTHROPIC_','STRIPE_','RESEND_'))}
    environment.update(PYTHONNOUSERSITE='1',PIP_CONFIG_FILE=os.devnull,PIP_NO_INDEX='1',
                       MACOSX_DEPLOYMENT_TARGET='14.0',ZERO_AR_DATE='1',
                       PKG_CONFIG_PATH=str(prefix/'lib/pkgconfig'),PKG_CONFIG_LIBDIR=str(prefix/'lib/pkgconfig'))

    def run(args):
        return run_logged(args,environment,log)

    run(['git','clone','--filter=blob:none','--no-checkout','https://github.com/PyAV-Org/PyAV.git',source])
    run(['git','-C',source,'checkout','--detach',PYAV_COMMIT])
    if run(['git','-C',source,'rev-parse','HEAD']).strip() != PYAV_COMMIT:
        raise ValueError('PyAV source differs from reviewed commit.')
    environment['SOURCE_DATE_EPOCH'] = run(['git','-C',source,'show','-s','--format=%ct',PYAV_COMMIT]).strip()
    environment['CFLAGS'] = '-ffile-prefix-map='+str(source)+'=/clipbot-build/pyav'
    environment['LDFLAGS'] = native_link_flags(target)
    environment['DYLD_LIBRARY_PATH' if target.startswith('macos-') else 'LD_LIBRARY_PATH'] = str(prefix/'lib')
    raw = output/'raw'
    raw.mkdir()
    run([sys.executable,'-I','-m','pip','--isolated','wheel','--no-index','--no-deps','--no-build-isolation','--wheel-dir',raw,source])
    built = list(raw.glob('av-*.whl'))
    if len(built) != 1:
        raise ValueError('Native decoder build must produce exactly one wheel.')
    repaired = output/'repaired'
    repaired.mkdir()
    if target.startswith('macos-'):
        run([Path(sys.executable).parent/'delocate-wheel','--require-archs','arm64' if target.endswith('arm64') else 'x86_64','--wheel-dir',repaired,built[0]])
    else:
        run([Path(sys.executable).parent/'auditwheel','repair','--plat','manylinux_2_39_x86_64','--wheel-dir',repaired,built[0]])
    wheels = list(repaired.glob('av-*.whl'))
    if len(wheels) != 1:
        raise ValueError('Native decoder repair must produce exactly one wheel.')
    wheel = wheels[0]
    validate_wheel_name(wheel,target)
    with wheel.open('rb') as stream:
        digest = hashlib.file_digest(stream,'sha256').hexdigest()
    requirements = output/'decoder.lock'
    requirements.write_text('av==18.0.0 --hash=sha256:'+digest+'\n')
    run([sys.executable,'-I','-m','pip','--isolated','install','--no-index','--no-deps','--require-hashes',
         '--only-binary=:all:','--find-links',repaired,'-r',requirements])
    verify_native_pyav(wheel)
    versions = json.loads(run([sys.executable,'-I','-c','import av,json; print(json.dumps({"version":av.__version__,"libraries":av.library_versions}))']))
    if versions['version'] != '18.0.0' or versions['libraries'].get('libavcodec',[None])[0] != 62:
        raise ValueError('Installed native decoder has unexpected library versions.')
    shutil.copyfile(wheel,output/'av-reviewed.whl')
    receipt = {'target':target,'pyavSourceCommit':PYAV_COMMIT,'registryCommit':BASELINE,
               'wheelFilename':wheel.name,'sha256':digest,'sizeBytes':wheel.stat().st_size,
               'installed':versions,'sourceComplete':False,'publicReleaseApproved':False}
    (output/'pyav-diagnostics.json').write_text(json.dumps(receipt,indent=2))
    print('Source-built native decoder matches reviewed wheel bytes. Source/packaging acceptance remains separate.')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--target',choices=sorted(TARGETS),required=True)
    parser.add_argument('--media-root',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args = parser.parse_args()
    try:
        build(args.target,args.media_root,args.output)
    except (OSError,ValueError,KeyError,subprocess.SubprocessError) as error:
        print('Native decoder build blocked:',str(error))
        return 1
    return 0


if __name__=='__main__':
    raise SystemExit(main())
