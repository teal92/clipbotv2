"""Build reviewed Linux desktop bindings without pip/Meson network resolution."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
import zipfile

ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0,str(ROOT))
from tools.build_native_runtime import download,extract_source
from tools.install_native_wheels import validate_snapshot,run_logged
from tools.native_dependency_snapshot import canonicalize_name,parse_wheel_filename
from tools.verify_native_release_inputs import verify_native_runtime,verify_binary_target
from worker.platforms.identity import current_target

SOURCE_ORDER=('pycairo','pygobject')


def wheel_command(python,source,output):
    return [str(python),'-I','-m','pip','--isolated','wheel','--no-index','--no-deps',
            '--no-build-isolation','--config-settings=setup-args=--wrap-mode=nodownload',
            '--config-settings=setup-args=-Dtests=false','--wheel-dir',str(output),str(source)]


def build(output,*,host_target=None):
    if (host_target or current_target())!='linux-x86_64':
        raise ValueError('Desktop compilation requires a matching Linux x86-64 host.')
    verify_native_runtime()
    snapshot=json.loads((ROOT/'packaging/platforms/linux-x86_64.dependencies.json').read_text())
    _,sources=validate_snapshot(snapshot,'linux-x86_64')
    sources={canonicalize_name(item['name']):item for item in sources}
    if set(sources)!={'av',*SOURCE_ORDER}:
        raise ValueError('Linux desktop source inventory differs from policy.')
    output=Path(output).absolute()
    if output.exists():
        raise ValueError('Use a new Linux desktop source-build directory.')
    output.mkdir(mode=0o700,parents=True)
    output=output.resolve()
    archives=output/'sources'
    archives.mkdir()
    wheelhouse=output/'wheels'
    wheelhouse.mkdir()
    environment={key:value for key,value in os.environ.items()
                 if not key.startswith(('CLIPBOT_','ANTHROPIC_','STRIPE_','RESEND_','PYTHON'))
                 and key not in {'CPATH','LIBRARY_PATH','LD_LIBRARY_PATH','PKG_CONFIG_PATH','PKG_CONFIG_LIBDIR','CFLAGS','CXXFLAGS','LDFLAGS'}}
    environment.update(PYTHONNOUSERSITE='1',PIP_NO_INDEX='1',PIP_CONFIG_FILE=os.devnull,
        PATH=str(Path(sys.executable).parent)+os.pathsep+'/usr/bin:/bin',
        PKG_CONFIG_LIBDIR='/usr/lib/x86_64-linux-gnu/pkgconfig:/usr/share/pkgconfig',
        PKG_CONFIG_PATH='/usr/lib/x86_64-linux-gnu/pkgconfig:/usr/share/pkgconfig',
        CFLAGS='-ffile-prefix-map='+str(output)+'=/clipbot-build/desktop')
    log=output/'build.log'
    built={}
    for name in SOURCE_ORDER:
        item=sources[name]
        record=item['artifact']
        archive=archives/record['filename']
        download(record,archive)
        source=extract_source(archive,output/('source-'+name))
        run_logged(wheel_command(sys.executable,source,wheelhouse),environment,log)
        matches=list(wheelhouse.glob(name+'-*.whl'))
        if len(matches)!=1:
            raise ValueError('Expected exactly one built Linux desktop wheel: '+name)
        wheel=matches[0]
        distribution,version,_,tags=parse_wheel_filename(wheel.name)
        if (canonicalize_name(distribution)!=name or str(version)!=item['version']
                or not any(tag.interpreter=='cp312' and tag.platform=='linux_x86_64' for tag in tags)):
            raise ValueError('Built Linux desktop wheel identity differs.')
        # Bind compiled architecture before local pip installs the new wheel.
        with zipfile.ZipFile(wheel) as package:
            libraries=[entry for entry in package.infolist() if entry.filename.endswith('.so')]
            if not libraries or sum(entry.file_size for entry in package.infolist())>100_000_000:
                raise ValueError('Invalid Linux desktop wheel payload.')
            for entry in libraries:
                verify_binary_target(package.read(entry),'linux-x86_64','Ubuntu 24.04')
        with wheel.open('rb') as stream:
            digest=hashlib.file_digest(stream,'sha256').hexdigest()
        lock=output/(name+'.lock')
        lock.write_text(item['name']+'=='+item['version']+' --hash=sha256:'+digest+'\n')
        run_logged([sys.executable,'-I','-m','pip','--isolated','install','--no-index','--no-deps',
                    '--only-binary=:all:','--require-hashes','--find-links',wheelhouse,'-r',lock],environment,log)
        built[item['name']]={'version':item['version'],'filename':wheel.name,'sha256':digest,'sizeBytes':wheel.stat().st_size}
    run_logged([sys.executable,'-I','-c',
        'import cairo,gi; gi.require_version("Gtk","3.0"); from gi.repository import Gtk; print("Linux native desktop binding imports passed")'],environment,log)
    receipt={'target':'linux-x86_64','wheels':built,'importsPassed':True,
             'sources':{item['name']:item['artifact'] for name,item in sources.items() if name in SOURCE_ORDER},
             'desktopChecks':'not-exercised','publicReleaseApproved':False}
    (output/'desktop-diagnostics.json').write_text(json.dumps(receipt,indent=2))
    print('Reviewed Linux desktop bindings built; real tray and desktop acceptance remain separate.')


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--output',type=Path,required=True)
    build(parser.parse_args().output)
