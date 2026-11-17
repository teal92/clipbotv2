"""Build native candidates only from a clean commit and verified input snapshot."""
import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from worker.platforms.identity import current_target
from tools.verify_native_release_inputs import NATIVE_TARGETS, verify_native_environment, verify_binary_target
from server.companion_download import FILENAMES


def run(args, **kwargs):
    return subprocess.run(args, check=True, cwd=ROOT, **kwargs)


def build(target, output, *, inputs_root=None):
    if current_target() != target:
        raise ValueError('Build this package on its matching native host and processor.')
    source = run(['git','rev-parse','HEAD'], capture_output=True, text=True).stdout.strip()
    if run(['git','status','--porcelain'], capture_output=True, text=True).stdout:
        raise ValueError('Native releases require clean committed source.')
    assets = Path(inputs_root).absolute() if inputs_root is not None else ROOT
    inputs = assets/f'packaging/platforms/{target}.inputs.json'
    manifest = json.loads(inputs.read_text())
    verify_native_environment(assets, manifest, target)
    output = output.absolute()
    if output.exists():
        raise ValueError('Use a new output directory; existing artifacts are never overwritten.')
    output.mkdir(parents=True)
    work = output/'work'
    work.mkdir()
    runtime_metadata=work/'native-release.json'
    runtime_metadata.write_text(json.dumps({'version':manifest['releaseVersion'],'target':target}))
    environment = {**os.environ, 'CLIPBOT_BUILD_TARGET':target, 'CLIPBOT_BUILD_VERSION':manifest['releaseVersion'],'CLIPBOT_BUILD_RECEIPT':str(runtime_metadata),'CLIPBOT_INPUT_ROOT':str(assets)}
    run([sys.executable,'-m','PyInstaller','--noconfirm','--distpath',str(work/'dist'),'--workpath',str(work/'build'),str(ROOT/'packaging/native-companion.spec')], env=environment)
    from packaging_audit import audit_bundle
    bundle = work/'dist'/('ClipBotCompanion.app' if target.startswith('macos-') else 'ClipBotCompanion')
    errors = audit_bundle(bundle, allow_internal_links=target.startswith('macos-'))
    if errors:
        raise ValueError('Native package audit failed: '+'; '.join(errors[:5]))
    checked=set()
    for path in bundle.rglob('*'):
        if not path.is_file() or path.resolve() in checked:continue
        checked.add(path.resolve())
        with path.open('rb') as stream:magic=stream.read(4)
        if magic in (b'\x7fELF',b'\xcf\xfa\xed\xfe',b'\xfe\xed\xfa\xcf',b'\xca\xfe\xba\xbe',b'\xca\xfe\xba\xbf'):
            if path.stat().st_size>200000000:raise ValueError('Native binary exceeds inspection limit.')
            verify_binary_target(path.read_bytes(),target,manifest['minimumOS'])
    destination = output/FILENAMES[target]
    if target.startswith('macos-'):
        run(['/usr/bin/hdiutil','create','-volname','ClipBot Companion','-srcfolder',str(bundle),'-ov','-format','UDZO',str(destination)])
    else:
        stage = work/'deb'
        (stage/'opt').mkdir(parents=True)
        shutil.copytree(bundle, stage/'opt/clipbot-companion', symlinks=False)
        (stage/'DEBIAN').mkdir()
        policy = json.loads((ROOT/'packaging/platforms/linux.json').read_text())
        control = f"Package: clipbot-companion\nVersion: {manifest['releaseVersion'].replace('-beta.','~beta')}\nArchitecture: amd64\nMaintainer: YOUR COMPANY NAME\nDepends: "+', '.join(policy['desktopPackages'])+'\nDescription: ClipBot Companion for Ubuntu and Linux Mint desktops\n'
        (stage/'DEBIAN/control').write_text(control)
        applications = stage/'usr/share/applications'
        applications.mkdir(parents=True)
        (applications/'clipbot-companion.desktop').write_text('[Desktop Entry]\nType=Application\nName=ClipBot Companion\nExec=/opt/clipbot-companion/ClipBotCompanion %u\nTerminal=false\nCategories=AudioVideo;\nMimeType=x-scheme-handler/clipbot-companion;\n')
        run(['/usr/bin/dpkg-deb','--root-owner-group','--build',str(stage),str(destination)])
    with destination.open('rb') as stream:
        digest = hashlib.file_digest(stream, 'sha256').hexdigest()
    receipt = {k:manifest[k] for k in ('target','releaseVersion','minimumOS')}
    receipt.update(version=receipt.pop('releaseVersion'),sha256=digest,sizeBytes=destination.stat().st_size,sourceCommit=source,channel='internal',signed=False,notarized=False,provenanceVerified=False,cleanMachineAccepted=False,cleanInstallPairedAccepted=False)
    # Verifying pinned inputs is necessary but does not by itself prove the full native build provenance.
    (output/'manifest.json').write_text(json.dumps(receipt, indent=2))
    print('Native candidate built. Signature, provenance and clean-machine acceptance remain separate release gates.')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--target', choices=sorted(NATIVE_TARGETS), required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--inputs-root', type=Path)
    args = parser.parse_args()
    try:
        build(args.target, args.output, inputs_root=args.inputs_root)
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        print('Native build blocked:', str(error))
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
