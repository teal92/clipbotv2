"""Assemble internal candidate inputs from the same verified native build job.

This generates facts and hashes, never public release or tester approval.
"""
import argparse
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import re
import shutil
import sys

ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0,str(ROOT))
from worker.platforms.identity import current_target
from tools.build_native_runtime import download, verify_source
from tools.install_native_wheels import validate_snapshot, run_logged
from tools.native_source_bundle import build_bundle
from tools.verify_native_release_inputs import NATIVE_TARGETS, verify_native_runtime, verify_native_approved, verify_native_environment
from tools.verify_release_inputs import verify_build_inventory
from tools.native_dependency_snapshot import canonicalize_name,parse_wheel_filename
from tools.build_native_media import profile_name


def final_lock(snapshot,source_hashes):
    approved,lines={},[]
    for item in snapshot['packages']:
        name,version,artifact=item['name'],item['version'],item['artifact']
        digest=artifact.get('sha256') if artifact['kind']=='wheel' else source_hashes.get(name)
        if not isinstance(digest,str) or not re.fullmatch('[a-f0-9]{64}',digest) or name in approved:
            raise ValueError('Exact reviewed source wheel hash is required for every native dependency.')
        approved[name]=version
        lines.append(name+'=='+version+' --hash=sha256:'+digest)
    return approved,'\n'.join(lines)+'\n'


def input_record(root,path,role):
    root,path=Path(root).resolve(),Path(path).absolute()
    if (not path.is_relative_to(root) or not path.resolve().is_relative_to(root)
            or any(part in {'.','..'} for part in path.relative_to(root).parts)
            or any(p.is_symlink() for p in (path,*path.parents))
            or not path.is_file() or not 0 < path.stat().st_size <= 2_000_000_000):
        raise ValueError('Unsafe, missing or empty native candidate input.')
    with path.open('rb') as stream:
        digest=hashlib.file_digest(stream,'sha256').hexdigest()
    return {'path':path.relative_to(root).as_posix(),'sha256':digest,'sizeBytes':path.stat().st_size,'role':role}


def supplemental_notices(name,version,*,root=ROOT):
    root=Path(root).resolve()
    policy=root/'packaging/platforms/native-supplemental-notices.json'
    if not 0<policy.stat().st_size<=100_000:
        raise ValueError('Native supplemental notice inventory exceeds limit.')
    value=json.loads(policy.read_text())
    if value.get('schemaVersion')!=1 or not isinstance(value.get('records'),list) or len(value['records'])>100:
        raise ValueError('Invalid supplemental notice inventory.')
    canonical=lambda text:re.sub('[-_.]+','-',text).lower()
    records=[item for item in value['records'] if canonical(item['package'])==canonical(name)]
    texts=[]
    for item in records:
        if item['version']!=version or not item['path'].startswith(('packaging/licenses/','packaging/native/licenses/')):
            raise ValueError('Supplemental license version or path differs from reviewed inventory.')
        path=root/item['path']
        record=input_record(root,path,'notice')
        if path.stat().st_size>2_000_000 or record['sha256']!=item['sha256']:
            raise ValueError('Supplemental license bytes differ from reviewed inventory.')
        texts.append(item['path']+'\n'+path.read_text(encoding='utf-8'))
    return '\n'.join(texts)


def package_notices(approved):
    texts=['ClipBot Companion native third-party notices\n'
           'Source records and matching media/runtime sources: licenses/native/corresponding-source.zip.\n'
           'FFmpeg renderer is a separate GPLv3 executable; PyAV uses the separate LGPL decoder.\n'
           'pystray is LGPLv3; its Python sources are supplied as replaceable external files.\n']
    for name,version in sorted(approved.items()):
        distribution=importlib.metadata.distribution(name)
        texts.append('\n=== '+name+' '+version+' ===\n')
        count=0
        for entry in distribution.files or []:
            parts=Path(str(entry)).parts
            if '..' in parts or not re.search(r'(?i)(licen[sc]e|copying|copyright|notice)',Path(str(entry)).name):
                continue
            path=Path(distribution.locate_file(entry))
            if path.is_symlink() or not path.is_file() or not 0 < path.stat().st_size <= 2_000_000:
                raise ValueError('Invalid installed package license record: '+name)
            texts.append(str(entry)+'\n'+path.read_text(encoding='utf-8',errors='replace'))
            count+=1
            if count>50:
                raise ValueError('Package notice inventory exceeds limit.')
        if count==0:
            extra=supplemental_notices(name,version)
            if not extra:
                raise ValueError('Missing complete package license text: '+name)
            texts.append(extra)
    return '\n'.join(texts)


def desktop_source_inputs(root,sources):
    root=Path(root).resolve()
    receipt_path=root/'desktop-diagnostics.json'
    if not 0<receipt_path.stat().st_size<=100_000:
        raise ValueError('Invalid Linux desktop receipt size.')
    receipt=json.loads(receipt_path.read_text())
    names={item['name'] for item in sources}
    if (receipt.get('target')!='linux-x86_64' or receipt.get('importsPassed') is not True
            or set(receipt.get('wheels',{}))!=names or set(receipt.get('sources',{}))!=names
            or {canonicalize_name(name) for name in names}!={'pycairo','pygobject'}):
        raise ValueError('Successful exact Linux desktop source receipt is required.')
    hashes,extra={},[]
    for item in sources:
        name,version,source=item['name'],item['version'],item['artifact']
        built=receipt['wheels'][name]
        if built.get('version')!=version or receipt['sources'][name]!=source:
            raise ValueError('Linux desktop source identity differs from pinned policy.')
        for directory,record in (('wheels',built),('sources',source)):
            filename=record.get('filename')
            if not isinstance(filename,str) or not re.fullmatch('[A-Za-z0-9_.+-]{1,180}',filename):
                raise ValueError('Unsafe Linux desktop artifact filename.')
            path=root/directory/filename
            input_record(root,path,'compiler' if directory=='wheels' else 'source')
            verify_source(path,record)
        distribution,wheel_version,_,tags=parse_wheel_filename(built['filename'])
        if (canonicalize_name(distribution)!=canonicalize_name(name) or str(wheel_version)!=version
                or not any(tag.interpreter=='cp312' and tag.platform=='linux_x86_64' for tag in tags)):
            raise ValueError('Linux desktop wheel target or version differs.')
        hashes[name]=built['sha256']
        extra.append((source,root/'sources'/source['filename']))
    return hashes,extra


def prepare(target,runtime_root,wheels_root,media_root,pyav_root,output,*,host_target=None,desktop_root=None):
    if target not in NATIVE_TARGETS or (host_target or current_target()) != target:
        raise ValueError('Candidate assembly requires a matching native host and processor.')
    verify_native_runtime()
    runtime_root,wheels_root,media_root,pyav_root=map(lambda p:Path(p).resolve(),(runtime_root,wheels_root,media_root,pyav_root))
    snapshot=json.loads((ROOT/f'packaging/platforms/{target}.dependencies.json').read_text())
    prebuilt,sources=validate_snapshot(snapshot,target)
    source_names={canonicalize_name(item['name']) for item in sources}
    extra_source_hashes,desktop_sources={},[]
    if target=='linux-x86_64' and source_names=={'av','pycairo','pygobject'} and desktop_root is not None:
        extra_source_hashes,desktop_sources=desktop_source_inputs(desktop_root,[item for item in sources if canonicalize_name(item['name'])!='av'])
    elif source_names != {'av'}:
        raise ValueError('Additional native source dependencies are not yet accepted.')
    decoder=json.loads((pyav_root/'pyav-diagnostics.json').read_text())
    if decoder.get('target')!=target:
        raise ValueError('Native decoder receipt target differs.')
    wheel=pyav_root/'av-reviewed.whl'
    verify_source(wheel,decoder)
    approved,lock=final_lock(snapshot,{'av':decoder['sha256'],**extra_source_hashes})
    verify_native_approved(approved,target)
    verify_build_inventory(approved)
    for item in prebuilt:
        verify_source(wheels_root/'wheels'/item['artifact']['filename'],item['artifact'])
    output=Path(output).absolute()
    if output.exists():
        raise ValueError('Use a new candidate asset directory.')
    output.mkdir(mode=0o700,parents=True)
    output=output.resolve()
    log=output/'assembly.log'
    environment={key:value for key,value in os.environ.items()
                 if not key.startswith(('CLIPBOT_','ANTHROPIC_','STRIPE_','RESEND_'))}
    environment.update(PYTHONNOUSERSITE='1',PIP_CONFIG_FILE=os.devnull,PIP_NO_INDEX='1',MACOSX_DEPLOYMENT_TARGET='14.0')
    platform=output/'packaging/platforms'
    platform.mkdir(parents=True)
    (platform/(target+'.approved.json')).write_text(json.dumps(approved,indent=2))
    (platform/(target+'.lock')).write_text(lock)
    tools=output/f'packaging/tools/native/{target}/bin'
    tools.mkdir(parents=True)
    media=json.loads((media_root/'media-diagnostics.json').read_text())
    if media.get('target') != target or media.get('mediaFeatureChecksPassed') is not True:
        raise ValueError('Checked media receipt is required.')
    for name in ('ffmpeg','ffprobe'):
        original=media_root/'tools'/name
        verify_source(original,media['tools'][name])
        shutil.copy2(original,tools/name)
    reviewed=tools.parent/'wheels'
    reviewed.mkdir()
    shutil.copyfile(wheel,reviewed/'av-reviewed.whl')
    # Freeze the exact reviewed yt-dlp distribution; no additional pip resolver.
    entry=output/'yt_dlp_entry.py'
    entry.write_text('from yt_dlp import main\nmain()\n')
    run_logged([sys.executable,'-m','PyInstaller','--noconfirm','--clean','--onefile','--name','yt-dlp',
                '--distpath',tools,'--workpath',output/'yt-dlp-work','--specpath',output,entry],environment,log)
    model=output/'worker/data/models/base'
    from worker.download_model import download as download_model
    download_model(model)
    from worker.model_integrity import MODEL_FILES,verify_model
    verify_model(model)
    records=json.loads((ROOT/'packaging/platforms/additional-source-records.json').read_text())
    extra=output/'additional-sources'
    extra.mkdir()
    extra_sources=list(desktop_sources)
    if desktop_sources:
        desktop_root=Path(desktop_root).resolve()
        for path,base in ((desktop_root/'desktop-diagnostics.json',desktop_root),
                          (desktop_root/'build.log',desktop_root),
                          (ROOT/'tools/build_native_linux_desktop.py',ROOT)):
            extra_sources.append((input_record(base,path,'source'),path))
    for name,record in records.items():
        path=extra/(name+('.tar.gz' if name=='pystray' else '.txt'))
        download(record,path)
        extra_sources.append((record,path))
    destination=output/f'packaging/native/{target}'
    destination.mkdir(parents=True)
    build_bundle(media_root,pyav_root,destination/'corresponding-source.zip',target,
                 runtime_root=runtime_root,extra_sources=extra_sources)
    notices=package_notices(approved)
    for profile in ('decoder','renderer'):
        share=media_root/'installed'/profile/profile_name(target,profile)/'share'
        for copyright_path in sorted(share.glob('*/copyright')):
            if copyright_path.is_symlink() or not 0 < copyright_path.stat().st_size <= 2_000_000:
                raise ValueError('Invalid native library copyright record.')
            notices+='\n=== '+profile+'/'+copyright_path.parent.name+' ===\n'+copyright_path.read_text(encoding='utf-8',errors='replace')
    notices+='\nWhisper base model: MIT, snapshot ebe41f70d5b6dfa9166e2c581c45c9c0cfc57b66\n'
    notices+=(extra/'whisper-model-license.txt').read_text()
    # Include runtime license texts from exactly the source trees compiled above.
    for folder,pattern in (('source-python','*/LICENSE'),('source-openssl','*/LICENSE.txt'),('source-libffi','*/LICENSE')):
        found=list((runtime_root/folder).glob(pattern))
        if len(found)!=1:
            raise ValueError('Native runtime license record missing: '+folder)
        notices+='\n=== '+folder+' ===\n'+found[0].read_text()
    (destination/'THIRD-PARTY-NOTICES.txt').write_text(notices,encoding='utf-8')
    paths=[(tools/name,'media') for name in ('ffmpeg','ffprobe','yt-dlp')]
    paths += [(model/name,'model') for name in MODEL_FILES]
    paths += [(platform/(target+'.approved.json'),'lock'),(platform/(target+'.lock'),'lock'),
              (reviewed/'av-reviewed.whl','compiler'),(destination/'corresponding-source.zip','source'),
              (destination/'THIRD-PARTY-NOTICES.txt','notice')]
    policy=json.loads((ROOT/('packaging/platforms/macos.json' if target.startswith('macos-') else 'packaging/platforms/linux.json')).read_text())
    manifest={'schemaVersion':1,'target':target,'releaseVersion':policy['releaseVersion'],
              'minimumOS':policy['candidateMinimumOS'],'sourceComplete':True,'dependencyLockComplete':True,
              'artifacts':[input_record(output,path,role) for path,role in paths]}
    (platform/(target+'.inputs.json')).write_text(json.dumps(manifest,indent=2))
    verify_native_environment(output,manifest,target)
    print('Internal candidate inputs verified. Public release and desktop acceptance remain unapproved.')


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--target',choices=sorted(NATIVE_TARGETS),required=True)
    for name in ('runtime-root','wheels-root','media-root','pyav-root','output'):
        parser.add_argument('--'+name,type=Path,required=True)
    parser.add_argument('--desktop-root',type=Path)
    arguments=parser.parse_args()
    prepare(arguments.target,arguments.runtime_root,arguments.wheels_root,arguments.media_root,arguments.pyav_root,arguments.output,desktop_root=arguments.desktop_root)
