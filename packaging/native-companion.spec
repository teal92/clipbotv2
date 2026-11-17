"""Native-only recipe. Input manifests are checked before dependency collection."""
import json
import os
from pathlib import Path
from PyInstaller.utils.hooks import collect_all, copy_metadata
from tools.verify_native_release_inputs import verify_native_environment

root = Path(SPECPATH).parent
assets = Path(os.environ.get('CLIPBOT_INPUT_ROOT',str(root)))
target = os.environ['CLIPBOT_BUILD_TARGET']
manifest = json.loads((assets/f'packaging/platforms/{target}.inputs.json').read_text())
verify_native_environment(assets, manifest, target)
runtime_metadata=Path(os.environ['CLIPBOT_BUILD_RECEIPT'])
if json.loads(runtime_metadata.read_text())!={'version':manifest['releaseVersion'],'target':target}:raise ValueError('Native runtime metadata differs from build inputs.')
packages = ['faster_whisper','ctranslate2','onnxruntime','tokenizers','pystray','PIL','yt_dlp','psutil','av']
datas, binaries, hidden = [], [], []
for package in packages:
    d, b, h = collect_all(package)
    datas += d
    binaries += b
    hidden += h
for distribution in ('av','faster-whisper','ctranslate2','onnxruntime','tokenizers','pystray','Pillow','yt-dlp','psutil','huggingface-hub','uvicorn','fastapi'):
    datas += copy_metadata(distribution)
from worker.model_integrity import MODEL_FILES
datas.extend((str(assets/'worker/data/models/base'/name), 'worker/data/models/base') for name in MODEL_FILES)
datas.append((str(assets/f'packaging/native/{target}/corresponding-source.zip'), 'licenses/native'))
datas.append((str(assets/f'packaging/native/{target}/THIRD-PARTY-NOTICES.txt'), '.'))
datas.append((str(runtime_metadata),'worker'))
for name in ('ffmpeg','ffprobe','yt-dlp'):
    binaries.append((str(assets/f'packaging/tools/native/{target}/bin/{name}'), 'bin'))
adapter = 'macos' if target.startswith('macos-') else 'linux'
hidden += ['worker.platforms.'+adapter, 'worker.platforms.'+adapter+'_secrets', 'uvicorn.logging','uvicorn.loops.asyncio','uvicorn.protocols.http.h11_impl','uvicorn.lifespan.on']
if target.startswith('macos-'):
    hidden += ['AppKit','Foundation','objc']
a = Analysis([str(root/'packaging/entry.py')],pathex=[str(root)],binaries=binaries,datas=datas,hiddenimports=hidden,excludes=['pytest','matplotlib','tkinter','torch','tensorflow'],noarchive=False,module_collection_mode={'pystray':'py'})
pyz = PYZ(a.pure)
exe = EXE(pyz,a.scripts,[],exclude_binaries=True,name='ClipBotCompanion',console=False,disable_windowed_traceback=True,target_arch='arm64' if target=='macos-arm64' else 'x86_64',argv_emulation=False)
coll = COLLECT(exe,a.binaries,a.datas,strip=False,upx=False,name='ClipBotCompanion')
if target.startswith('macos-'):
    app = BUNDLE(coll,name='ClipBotCompanion.app',bundle_identifier='com.yourcompany.clipbot.companion',info_plist={'CFBundleShortVersionString':manifest['releaseVersion'].split('-')[0],'LSMinimumSystemVersion':manifest['minimumOS'],'LSUIElement':True,'CFBundleURLTypes':[{'CFBundleURLName':'ClipBot pairing','CFBundleURLSchemes':['clipbot-companion']}]})
