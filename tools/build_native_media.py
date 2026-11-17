"""Compile candidate native media inputs; source/license acceptance stays separate."""
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
from worker.platforms.identity import current_target
from tools.verify_native_release_inputs import verify_binary_target

TARGETS = {'macos-arm64','macos-x86_64','linux-x86_64'}
BASELINE = 'c52f7bd748185ef0e0daf033d9f2ddfc8a3449ea'


def profile_name(target, profile):
    if target not in TARGETS or profile not in {'decoder','renderer'}:
        raise ValueError('Unsupported native media target/profile.')
    return 'clipbot-'+target.replace('_','-')+'-'+profile


def triplet(target, profile):
    if target not in TARGETS or profile not in {'decoder','renderer'}:
        raise ValueError('Unsupported native media target/profile.')
    arch = 'arm64' if target == 'macos-arm64' else 'x64'
    values = [f'set(VCPKG_TARGET_ARCHITECTURE {arch})', 'set(VCPKG_CRT_LINKAGE dynamic)',
              'set(VCPKG_LIBRARY_LINKAGE '+('dynamic' if profile=='decoder' else 'static')+')',
              'set(VCPKG_BUILD_TYPE release)', 'set(VCPKG_ENV_PASSTHROUGH PKG_CONFIG_LIBDIR)']
    if target.startswith('macos-'):
        values += ['set(VCPKG_CMAKE_SYSTEM_NAME Darwin)', 'set(VCPKG_OSX_DEPLOYMENT_TARGET 14.0)',
                   'set(VCPKG_OSX_ARCHITECTURES '+('arm64' if arch=='arm64' else 'x86_64')+')']
    else:
        values += ['set(VCPKG_CMAKE_SYSTEM_NAME Linux)']
    return '\n'.join(values)+'\n'


def profile_environment(base, output, target, profile):
    triplet(target,profile)  # Validate before constructing paths.
    prefix = Path(output)/'installed'/profile/profile_name(target,profile)
    directories = os.pathsep.join(str(prefix/path) for path in ('lib/pkgconfig','share/pkgconfig'))
    return {**base,'PKG_CONFIG_LIBDIR':directories,'PKG_CONFIG_PATH':directories}


def hashed_file(path):
    with path.open('rb') as stream:
        return {'sha256':hashlib.file_digest(stream,'sha256').hexdigest(),'sizeBytes':path.stat().st_size}


def build(target, output, *, host_target=None):
    if target not in TARGETS or (host_target or current_target()) != target:
        raise ValueError('Media compilation requires a matching native host and processor.')
    output = Path(output).absolute()
    if output.exists():
        raise ValueError('Media compilation requires a new output directory.')
    output.mkdir(mode=0o700,parents=True)
    output = output.resolve()
    log_path = output/'build.log'
    commands = []
    env = {key:value for key,value in os.environ.items() if key not in {
        'PKG_CONFIG_PATH','PKG_CONFIG_LIBDIR','CMAKE_PREFIX_PATH','CPATH','LIBRARY_PATH',
        'CFLAGS','CXXFLAGS','CPPFLAGS','LDFLAGS'}}
    env.update({'VCPKG_DISABLE_METRICS':'1','VCPKG_BINARY_SOURCES':'clear',
           'VCPKG_MAX_CONCURRENCY':str(min(os.cpu_count() or 1,4)),
           'MACOSX_DEPLOYMENT_TARGET':'14.0'})

    def run(args, cwd=output, capture=False):
        commands.append({'args':list(map(str,args)), 'cwd':str(cwd)})
        if capture:
            result = subprocess.run(list(map(str,args)),cwd=cwd,env=env,check=True,capture_output=True,text=True,timeout=120)
            with log_path.open('a',encoding='utf-8') as log:
                log.write(result.stdout+result.stderr)
            return result.stdout+result.stderr
        with log_path.open('ab') as log:
            subprocess.run(list(map(str,args)),cwd=cwd,env=env,check=True,stdout=log,stderr=subprocess.STDOUT,timeout=2100)

    registry = output/'vcpkg'
    run(['git','clone','--filter=blob:none','--no-checkout','https://github.com/microsoft/vcpkg.git',registry])
    run(['git','checkout','--detach',BASELINE],cwd=registry)
    if run(['git','rev-parse','HEAD'],cwd=registry,capture=True).strip() != BASELINE:
        raise ValueError('Native media registry commit differs from reviewed baseline.')
    run(['./bootstrap-vcpkg.sh','-disableMetrics'],cwd=registry)
    triplets = output/'triplets'
    triplets.mkdir()
    overlays = output/'overlays'
    shutil.copytree(ROOT/'packaging/native/overlays',overlays)
    profiles = {}
    for profile in ('decoder','renderer'):
        source = ROOT/'packaging/native'/('decoder' if profile=='decoder' else 'native-renderer')/'vcpkg.json'
        manifest = json.loads(source.read_text())
        if manifest['builtin-baseline'] != BASELINE:
            raise ValueError('Media profile differs from reviewed registry baseline.')
        name = profile_name(target,profile)
        (triplets/(name+'.cmake')).write_text(triplet(target,profile))
        project = output/'profiles'/profile
        project.mkdir(parents=True)
        shutil.copyfile(source,project/'vcpkg.json')
        installed = output/'installed'/profile
        env.update(profile_environment(env,output,target,profile))
        run([registry/'vcpkg','install','--triplet='+name,'--overlay-triplets='+str(triplets),
             '--overlay-ports='+str(overlays),
             '--x-manifest-root='+str(project),'--x-install-root='+str(installed),
             '--downloads-root='+str(output/'downloads'),'--x-buildtrees-root='+str(output/'buildtrees'/profile),
             '--x-packages-root='+str(output/'packages'/profile),'--disable-metrics'])
        profiles[profile] = {'triplet':name,'installed':str(installed/name)}
    tools = output/'tools'
    tools.mkdir()
    renderer = Path(profiles['renderer']['installed'])
    for name in ('ffmpeg','ffprobe'):
        source = renderer/'tools/ffmpeg'/name
        if not source.is_file() or source.is_symlink() or source.stat().st_size > 200_000_000:
            raise ValueError('Native media tool missing or unsuitable for inspection.')
        verify_binary_target(source.read_bytes(), target, '14.0' if target.startswith('macos-') else 'Ubuntu 24.04')
        shutil.copy2(source,tools/name)
    version = run([tools/'ffmpeg','-version'],capture=True)
    protocols = run([tools/'ffmpeg','-hide_banner','-protocols'],capture=True)
    filters = run([tools/'ffmpeg','-hide_banner','-filters'],capture=True)
    encoders = run([tools/'ffmpeg','-hide_banner','-encoders'],capture=True)
    if ('ffmpeg version 8.1.2' not in version or '\n  https\n' not in protocols
            or 'libx264' not in encoders or 'subtitles' not in filters):
        raise ValueError('Native renderer lacks expected version, TLS, subtitles or H.264 support.')
    from tools.probe_native_tls import probe as probe_tls
    tls_checks = probe_tls(tools/'ffmpeg')
    # Keep every actual dependency/version, license, downloaded source and build
    # output for subsequent review. Do not turn these into a complete source claim.
    files = {}
    for directory in ('downloads','profiles','triplets','overlays','installed'):
        for path in (output/directory).rglob('*'):
            if path.is_symlink() or not path.is_file():
                continue
            decoder_install = Path(profiles['decoder']['installed'])
            if directory=='installed' and not (path.is_relative_to(decoder_install) or path.name=='copyright' or '/vcpkg/' in path.as_posix()):
                continue
            files[path.relative_to(output).as_posix()] = hashed_file(path)
    receipt = {'target':target,'registryCommit':BASELINE,'profiles':profiles,'files':files,
               'commands':commands,'tools':{name:hashed_file(tools/name) for name in ('ffmpeg','ffprobe')},
               'ffmpegVersionOutput':version,'compiler':run(['cc','--version'],capture=True),'tlsChecks':tls_checks,
               'mediaFeatureChecksPassed':True,'sourceComplete':False,'provenanceVerified':False,
               'packagedAcceptance':False,'publicReleaseApproved':False}
    (output/'media-diagnostics.json').write_text(json.dumps(receipt,indent=2))
    print('Native media inputs compiled and feature checks passed; source review and packaged acceptance remain required.')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--target',choices=sorted(TARGETS),required=True)
    parser.add_argument('--output',type=Path,required=True)
    args = parser.parse_args()
    try:
        build(args.target,args.output)
    except (OSError,ValueError,subprocess.SubprocessError) as error:
        print('Native media compilation blocked:',str(error))
        return 1
    return 0


if __name__=='__main__':
    raise SystemExit(main())
