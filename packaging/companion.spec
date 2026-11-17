from pathlib import Path
import json
from tools.verify_release_inputs import verify_packaging_inputs
from PyInstaller.utils.hooks import collect_all,collect_data_files,copy_metadata
root=Path(SPECPATH).parent
verify_packaging_inputs(root,json.loads((root/'packaging/release-inputs.json').read_text(encoding='utf-8')))
packages=['faster_whisper','ctranslate2','onnxruntime','tokenizers','pystray','PIL','yt_dlp','psutil']
datas=[];binaries=[];hidden=[]
for package in packages:
 d,b,h=collect_all(package);datas+=d;binaries+=b;hidden+=h
for name in ['av','faster-whisper','ctranslate2','onnxruntime','tokenizers','pystray','Pillow','yt-dlp','psutil','huggingface-hub','uvicorn','fastapi']:
 datas+=copy_metadata(name)
from worker.model_integrity import MODEL_FILES
datas.extend((str(root/'worker/data/models/base'/name),'worker/data/models/base') for name in MODEL_FILES)
datas.append((str(root/'packaging/THIRD-PARTY-NOTICES.txt'),'.'))
datas.append((str(root/'packaging/licenses'),'licenses'))
datas.append((str(root/'packaging/native/corresponding-source.zip'),'licenses/native'))
for name in ('msvcp140.dll','msvcp140_1.dll','vcruntime140.dll','vcruntime140_1.dll'):
 binaries.append((str(root/'packaging/tools/runtime'/name),'.'))
for name in ('ffmpeg','ffprobe'):
 source=root/'packaging/tools'/f'{name}.exe';binaries.append((str(source),'bin'))
binaries.append((str(root/'packaging/tools/yt-dlp.exe'),'bin'))
a=Analysis([str(root/'packaging/entry.py')],pathex=[str(root)],binaries=binaries,datas=datas,hiddenimports=hidden+['worker.platforms.windows','uvicorn.logging','uvicorn.loops.asyncio','uvicorn.protocols.http.h11_impl','uvicorn.lifespan.on'],excludes=['pytest','matplotlib','tkinter','torch','tensorflow'],noarchive=False)
pyz=PYZ(a.pure)
exe=EXE(pyz,a.scripts,[],exclude_binaries=True,name='ClipBotCompanion',console=False,disable_windowed_traceback=True)
coll=COLLECT(exe,a.binaries,a.datas,strip=False,upx=False,name='ClipBotCompanion')
