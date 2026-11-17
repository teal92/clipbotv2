"""Match native source archives to actual SPDX resources and preserve recipes.

Completeness here means recorded native decoder/renderer resources and build
recipes are present. It is not customer acceptance or a legal certification.
"""
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys
import tarfile
from urllib.parse import urlsplit
import zipfile

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0,str(ROOT))
from tools.build_native_media import BASELINE, TARGETS, profile_name
from tools.build_native_pyav import PYAV_COMMIT
from tools.build_native_runtime import read_pins as read_runtime_pins, verify_source


def runtime_sources(runtime_root):
    root = Path(runtime_root)
    entries = {}
    for record in read_runtime_pins().values():
        name = Path(urlsplit(record['url']).path).name
        path = root/'sources'/name
        verify_source(path,record)
        entries['runtime/sources/'+name] = path
    return entries


def archive_index(directory):
    directory = Path(directory)
    if not directory.is_dir():
        raise ValueError('Native source downloads are missing.')
    result, total = {}, 0
    for path in sorted(directory.rglob('*')):
        if path.is_symlink() or not path.is_file() or not path.name.endswith(('.tar.gz','.tar.xz','.tar.bz2','.tgz','.zip')):
            continue
        total += path.stat().st_size
        if total > 2_000_000_000:
            raise ValueError('Native source inventory exceeds limits.')
        for algorithm in ('SHA256','SHA512'):
            with path.open('rb') as stream:
                digest = hashlib.file_digest(stream,algorithm.lower()).hexdigest()
            result.setdefault((algorithm,digest),path)
    return result


def matching_resources(packages, index):
    matched = []
    for resource in packages:
        if not resource.get('SPDXID','').startswith('SPDXRef-resource-'):
            continue
        checksums = []
        for checksum in resource.get('checksums',[]):
            algorithm, value = checksum.get('algorithm'), checksum.get('checksumValue')
            if algorithm not in {'SHA256','SHA512'}:
                continue
            if not isinstance(value,str) or not re.fullmatch('[a-f0-9]{'+('64' if algorithm=='SHA256' else '128')+'}',value):
                raise ValueError('Invalid native source checksum.')
            checksums.append((algorithm,value))
        if not checksums:
            raise ValueError('Matching source requires strong resource checksums.')
        paths = {index.get(key) for key in checksums}
        if None in paths or len(paths) != 1:
            raise ValueError('Matching source archive is missing or differs from SPDX checksums.')
        matched.append((resource,paths.pop()))
    return matched


def validate_recipe_tar(data):
    if len(data) > 5_000_000:
        raise ValueError('Native source recipe exceeds limit.')
    with tarfile.open(fileobj=io.BytesIO(data),mode='r:') as archive:
        for count,entry in enumerate(archive):
            parts = entry.name.rstrip('/').split('/')
            if (count > 3000 or not entry.name or '\\' in entry.name or ':' in entry.name
                    or PurePosixPath(entry.name).is_absolute() or any(part in {'','.','..'} for part in parts)
                    or not (entry.isdir() or entry.isfile())):
                raise ValueError('Unsafe native build recipe member.')


def build_bundle(media_root, pyav_root, destination, target, *, runtime_root=None, extra_sources=None):
    if target not in TARGETS:
        raise ValueError('Unsupported native source target.')
    media_root, pyav_root, destination = Path(media_root).resolve(), Path(pyav_root).resolve(), Path(destination)
    receipt_path = media_root/'media-diagnostics.json'
    if not receipt_path.is_file() or receipt_path.stat().st_size > 1_000_000:
        raise ValueError('Native media build evidence is missing.')
    receipt = json.loads(receipt_path.read_text())
    if receipt.get('target') != target or receipt.get('registryCommit') != BASELINE or receipt.get('mediaFeatureChecksPassed') is not True:
        raise ValueError('Native source target or registry does not match the checked build.')
    pyav_receipt = pyav_root/'pyav-diagnostics.json'
    if not pyav_receipt.is_file() or pyav_receipt.stat().st_size > 100_000:
        raise ValueError('Native PyAV build evidence is missing.')
    if json.loads(pyav_receipt.read_text()).get('pyavSourceCommit') != PYAV_COMMIT:
        raise ValueError('Native PyAV source differs from reviewed commit.')
    archives = archive_index(media_root/'downloads')
    if runtime_root is None or extra_sources is None:
        raise ValueError('Native runtime and additional library source records are required.')
    entries, records = runtime_sources(runtime_root), []
    entries['runtime/runtime-diagnostics.json'] = Path(runtime_root)/'runtime-diagnostics.json'
    entries['runtime/build.log'] = Path(runtime_root)/'build.log'
    for record,path in extra_sources:
        path = Path(path)
        verify_source(path,record)
        entries['python-library-sources/'+path.name] = path
    for profile in ('decoder','renderer'):
        prefix = media_root/'installed'/profile/profile_name(target,profile)
        share = prefix/'share'
        packages = list(share.glob('*/vcpkg.spdx.json'))
        if not packages:
            raise ValueError('Native package source evidence is incomplete.')
        for path in sorted(packages):
            name = path.parent.name
            if not re.fullmatch(r'[a-z0-9][a-z0-9-]{0,79}',name):
                raise ValueError('Unsafe native source package name.')
            copyright_path = path.parent/'copyright'
            if not copyright_path.is_file() or not 0 < copyright_path.stat().st_size <= 5_000_000 or path.stat().st_size > 1_000_000:
                raise ValueError('Native source copyright or SPDX record is missing.')
            document = json.loads(path.read_text())
            port = next((p for p in document.get('packages',[]) if p.get('SPDXID')=='SPDXRef-port'),None)
            if not port or port.get('name') != name:
                raise ValueError('Native source package identity is incomplete.')
            resources = matching_resources(document['packages'],archives)
            base = f'package-records/{profile}/{name}'
            entries[base+'/vcpkg.spdx.json'] = path
            entries[base+'/copyright'] = copyright_path
            matched = []
            for resource,archive in resources:
                digest = hashlib.sha256(archive.read_bytes()).hexdigest()
                archive_name = 'resources/'+digest[:16]+'-'+archive.name
                if not re.fullmatch(r'[A-Za-z0-9_.+/-]+',archive_name):
                    raise ValueError('Unsafe native source archive name.')
                entries[archive_name] = archive
                matched.append({'source':resource.get('downloadLocation'),'archive':archive_name,'sha256':digest})
            if name == 'libass':
                overlay = media_root/'overlays/libass'
                if not (overlay/'UPSTREAM.json').is_file():
                    raise ValueError('Native subtitle overlay source record is missing.')
                for item in overlay.iterdir():
                    if item.is_symlink() or not item.is_file():
                        raise ValueError('Unsafe native overlay source.')
                    entries[base+'/port/'+item.name] = item
            else:
                location = port.get('downloadLocation','')
                tree = re.fullmatch(r'git\+https://github\.com/[Mm]icrosoft/vcpkg@([a-f0-9]{40})',location)
                if not tree:
                    raise ValueError('Native package build recipe lacks an immutable source tree.')
                registry = media_root/'vcpkg'
                kind = subprocess.run(['git','-C',str(registry),'cat-file','-t',tree[1]],capture_output=True,text=True,check=True,timeout=60).stdout.strip()
                if kind != 'tree':
                    raise ValueError('Native package recipe is not a Git tree.')
                data = subprocess.run(['git','-C',str(registry),'archive','--format=tar',tree[1]],capture_output=True,check=True,timeout=60).stdout
                validate_recipe_tar(data)
                entries[base+'/port-recipe.tar'] = data
            records.append({'profile':profile,'name':name,'version':port.get('versionInfo'),
                            'license':port.get('licenseConcluded'),'resources':matched})
    if not any(item['name']=='ffmpeg' and item['profile']=='decoder' for item in records) or not any(item['name']=='ffmpeg' and item['profile']=='renderer' for item in records):
        raise ValueError('Both native FFmpeg source profiles are required.')
    source = pyav_root/'source'
    actual = subprocess.run(['git','-C',str(source),'rev-parse','HEAD'],capture_output=True,text=True,check=True,timeout=60).stdout.strip()
    if actual != PYAV_COMMIT:
        raise ValueError('PyAV corresponding source commit differs.')
    # The public, immutable PyAV source archive contains its build scripts and license.
    pyav_tar = subprocess.run(['git','-C',str(source),'archive','--format=tar',PYAV_COMMIT],capture_output=True,check=True,timeout=60).stdout
    if len(pyav_tar) > 25_000_000:
        raise ValueError('PyAV source archive exceeds limit.')
    entries['pyav/source.tar'] = pyav_tar
    entries['build-records/media.json'] = receipt_path
    entries['build-records/pyav.json'] = pyav_receipt
    entries['build-records/media-build.log'] = media_root/'build.log'
    entries['build-records/pyav-build.log'] = pyav_root/'build.log'
    for relative in ('tools/build_native_media.py','tools/build_native_pyav.py','tools/build_native_runtime.py',
                     'tools/native_dependency_snapshot.py','tools/install_native_wheels.py','tools/verify_native_release_inputs.py',
                     'tools/dependency_policy.py','tools/verify_release_inputs.py','tools/native_source_bundle.py','worker/platforms/identity.py',
                     'worker/platforms/__init__.py','packaging/native/decoder/vcpkg.json','packaging/native/native-renderer/vcpkg.json',
                     f'packaging/platforms/{target}.dependencies.json','packaging/platforms/runtime-sources.json',
                     'packaging/platforms/desktop-package-versions.json'):
        entries['clipbot-build/'+relative] = ROOT/relative
    entries['clipbot-build/packaging/platforms/additional-source-records.json'] = ROOT/'packaging/platforms/additional-source-records.json'
    entries['clipbot-build/packaging/approved-worker-build.json'] = ROOT/'packaging/approved-worker-build.json'
    for path in (media_root/'triplets').glob('*.cmake'):
        entries['clipbot-build/triplets/'+path.name] = path
    manifest = {'target':target,'registryCommit':BASELINE,'pyavSourceCommit':PYAV_COMMIT,
                'nativePackages':records,'sourceRecordsComplete':True,'publicReleaseApproved':False}
    entries['SOURCE-MANIFEST.json'] = json.dumps(manifest,indent=2).encode()
    entries['START-HERE.txt'] = (f'ClipBot native source records for {target}.\n'
        'Renderer FFmpeg uses x264/OpenSSL and GPL version 3; decoder FFmpeg is a separate dynamic LGPL build.\n'
        'Package copyright/SPDX records, checksum-matched source archives, exact port recipes, native triplets and PyAV source are included.\n'
        f'Rebuild with vcpkg registry {BASELINE}; see clipbot-build/tools/build_native_media.py and build_native_pyav.py.\n'
        'This archive records native source/build inputs; it is not signing, application acceptance or a legal certification.\n').encode()
    destination.parent.mkdir(parents=True,exist_ok=True)
    handle = destination.open('xb')
    try:
        with handle, zipfile.ZipFile(handle,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=9) as output:
            total = 0
            for name,value in sorted(entries.items()):
                size = len(value) if isinstance(value,bytes) else value.stat().st_size
                total += size
                if total > 1_000_000_000:
                    raise ValueError('Native source bundle exceeds limit.')
                if isinstance(value,bytes):
                    output.writestr(name,value)
                else:
                    if value.is_symlink():
                        raise ValueError('Unsafe native source input link.')
                    output.write(value,name)
    except BaseException:
        destination.unlink(missing_ok=True)
        raise
    return manifest
