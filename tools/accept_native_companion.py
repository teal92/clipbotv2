"""Internal packaged checks. Headless CI never grants desktop acceptance."""
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import struct
import sys
import tempfile
import wave

ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0,str(ROOT))
from packaging_audit import audit_bundle
from worker.platforms.identity import current_target
from tools.probe_native_tls import probe as probe_tls
from tools.verify_native_release_inputs import NATIVE_TARGETS,verify_binary_target


def check_artifact(artifact,receipt,target,source):
    artifact=Path(artifact)
    if (receipt.get('target')!=target or receipt.get('sourceCommit')!=source
            or receipt.get('channel')!='internal' or artifact.is_symlink() or not artifact.is_file()
            or artifact.stat().st_size!=receipt.get('sizeBytes') or not 0<artifact.stat().st_size<=2_000_000_000):
        raise ValueError('Native artifact target, source or size differs from the internal build receipt.')
    with artifact.open('rb') as stream:
        if hashlib.file_digest(stream,'sha256').hexdigest()!=receipt.get('sha256'):
            raise ValueError('Native artifact hash differs from build receipt.')


def check_diagnostics(value):
    required=('ffmpeg','ffprobe','captureInstalled','transcriptionInstalled','metricsInstalled',
              'modelDownloaded','modelLoads','mediaTranscribes','rollingClipPasses',
              'candidatePreviewPasses','verticalReviewPasses')
    if any(value.get(name) is not True for name in required):
        raise ValueError('Packaged model, tools, transcription, rolling capture or rendering failed.')


def unique_file(root,name):
    matches={path.resolve() for path in root.rglob(name) if path.is_file()}
    if len(matches)!=1:
        raise ValueError('Packaged native component missing or ambiguous: '+name)
    path=matches.pop()
    if not path.is_relative_to(root.resolve()):
        raise ValueError('Packaged native component escapes bundle.')
    return path


def synthetic_sources(directory,*,seconds=80):
    if type(seconds) is not int or not 1<=seconds<=80:
        raise ValueError('Synthetic acceptance media duration exceeds limits.')
    directory=Path(directory)
    video,audio=directory/'synthetic.y4m',directory/'synthetic.wav'
    with video.open('xb') as output:
        output.write(b'YUV4MPEG2 W320 H180 F5:1 Ip A1:1 C420jpeg\n')
        for frame in range(seconds*5):
            output.write(b'FRAME\n'+bytes([16+frame%200])*(320*180)+bytes([128])*(320*180//2))
    with audio.open('xb') as handle,wave.open(handle,'wb') as recording:
        recording.setnchannels(1)
        recording.setsampwidth(2)
        recording.setframerate(16000)
        tone=b''.join(struct.pack('<h',int(math.sin(2*math.pi*440*i/16000)*2048)) for i in range(16000))
        for _ in range(seconds):
            recording.writeframesraw(tone)
    return video,audio


def synthetic_arguments(ffmpeg,video,audio,output,*,seconds=80):
    if type(seconds) is not int or not 1<=seconds<=80:
        raise ValueError('Synthetic acceptance media duration exceeds limits.')
    return list(map(str,[ffmpeg,'-nostdin','-v','error','-f','yuv4mpegpipe','-i',video,'-i',audio,
        '-t',seconds,'-map','0:v:0','-map','1:a:0','-c:v','libx264','-preset','ultrafast','-g','25',
        '-c:a','aac','-threads','2',output]))


def accept(target,artifact,manifest_path,report,*,host_target=None):
    if target not in NATIVE_TARGETS or (host_target or current_target())!=target:
        raise ValueError('Packaged checks require a matching native host and processor.')
    report=Path(report)
    if report.exists():
        raise ValueError('Use a new acceptance report path.')
    source=subprocess.run(['git','-C',str(ROOT),'rev-parse','HEAD'],capture_output=True,text=True,check=True,timeout=20).stdout.strip()
    if not 0<Path(manifest_path).stat().st_size<=200_000:
        raise ValueError('Native build receipt exceeds inspection limit.')
    receipt=json.loads(Path(manifest_path).read_text())
    check_artifact(artifact,receipt,target,source)
    checks={}
    result={'target':target,'sourceCommit':source,'sha256':receipt['sha256'],'checks':checks,
            'automatedChecksPassed':False,'cleanMachineAccepted':False,'cleanInstallPairedAccepted':False,
            'desktopChecks':'not-exercised','publicReleaseApproved':False}
    try:
        with tempfile.TemporaryDirectory(prefix='clipbot-packaged-check-') as temporary:
            temporary=Path(temporary).resolve()
            mounted=False
            image=temporary/'image'
            image.mkdir()
            try:
                if target.startswith('macos-'):
                    subprocess.run(['/usr/bin/hdiutil','attach','-readonly','-nobrowse','-mountpoint',str(image),str(Path(artifact).resolve())],check=True,capture_output=True,timeout=60)
                    mounted=True
                    original=image/'ClipBotCompanion.app'
                    if not original.is_dir():
                        raise ValueError('Mac disk image does not contain the installable application at its root.')
                else:
                    subprocess.run(['/usr/bin/dpkg-deb','--extract',str(Path(artifact).resolve()),str(image)],check=True,capture_output=True,timeout=60)
                    original=image/'opt/clipbot-companion'
                errors=audit_bundle(original,allow_internal_links=target.startswith('macos-'))
                if errors:
                    raise ValueError('Packaged content audit failed: '+'; '.join(errors[:5]))
                # Exercise the copied installation, never execute from a DMG.
                bundle=temporary/('ClipBotCompanion.app' if target.startswith('macos-') else 'ClipBotCompanion')
                shutil.copytree(original,bundle,symlinks=True)
            finally:
                if mounted:
                    subprocess.run(['/usr/bin/hdiutil','detach',str(image)],check=True,capture_output=True,timeout=60)
            checks['contentAudit']='passed'
            executable=(bundle/'Contents/MacOS/ClipBotCompanion' if target.startswith('macos-') else bundle/'ClipBotCompanion')
            verify_binary_target(executable.read_bytes(),target,receipt['minimumOS'])
            metadata=json.loads(unique_file(bundle,'native-release.json').read_text())
            if metadata!={'version':receipt['version'],'target':target}:
                raise ValueError('Frozen runtime version/target differs from the artifact receipt.')
            if not list(bundle.rglob('pystray/_base.py')):
                raise ValueError('Replaceable tray library source is missing from the application.')
            checks['architectureVersionAndLibrarySource']='passed'
            ffmpeg=unique_file(bundle,'ffmpeg')
            checks['packagedTls']=probe_tls(ffmpeg)['checks']
            environment={key:value for key,value in os.environ.items()
                         if not key.startswith(('CLIPBOT_','ANTHROPIC_','STRIPE_','RESEND_','HF_','HUGGINGFACE_'))
                         and key not in {'PYTHONPATH','PYTHONHOME','DYLD_LIBRARY_PATH','LD_LIBRARY_PATH'}}
            home=temporary/'home'
            home.mkdir(mode=0o700)
            environment.update(HOME=str(home),XDG_DATA_HOME=str(home/'data'),XDG_CONFIG_HOME=str(home/'config'),
                               HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1')
            media=temporary/'probe.mp4'
            video,audio=synthetic_sources(temporary)
            subprocess.run(synthetic_arguments(ffmpeg,video,audio,media),
                env=environment,check=True,capture_output=True,timeout=120)
            candidate=temporary/'candidate.json'
            candidate.write_text(json.dumps({'start':0,'end':15,'title':'Synthetic native acceptance clip'}))
            subprocess.run([str(executable),'--diagnose-media',str(media),'--diagnose-rolling',
                '--diagnose-preview-candidate',str(candidate)],env=environment,check=True,capture_output=True,timeout=300)
            diagnostics=(home/'Library/Application Support/ClipBotCompanion/diagnostics.json' if target.startswith('macos-')
                         else home/'data/ClipBotCompanion/diagnostics.json')
            check_diagnostics(json.loads(diagnostics.read_text()))
            checks['frozenModelTranscriptionCaptureAndRender']='passed'
            result['automatedChecksPassed']=True
    finally:
        report.parent.mkdir(parents=True,exist_ok=True)
        with report.open('x') as output:
            json.dump(result,output,indent=2)
    print('Packaged automated checks passed. Desktop installation, pairing and update acceptance remain separate.')
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--target',choices=sorted(NATIVE_TARGETS),required=True)
    for name in ('artifact','manifest','report'):
        parser.add_argument('--'+name,type=Path,required=True)
    args=parser.parse_args()
    accept(args.target,args.artifact,args.manifest,args.report)
