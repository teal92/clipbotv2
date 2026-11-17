"""Windowless customer tray entry point and encrypted per-user pairing handoff."""
from .tools import media_tool
import argparse,os,secrets,sys,threading,time,webbrowser
from pathlib import Path
from .platforms import integration
from .windows_integration import parse_pair_link
from .credentials import load,save
from .client import configured_origin

def finish_shutdown(server,thread,instance):
 server.should_exit=True;thread.join();instance.close()

def parse_launch_args(argv=None):
 parser=argparse.ArgumentParser();parser.add_argument('--background',action='store_true');parser.add_argument('--handoff');parser.add_argument('--diagnose',action='store_true');parser.add_argument('--diagnose-media');parser.add_argument('--diagnose-preview-candidate');parser.add_argument('--diagnose-rolling',action='store_true');parser.add_argument('links',nargs='*');args=parser.parse_args(argv)
 # A bad link is data from outside; report it politely instead of exiting through argparse (the windowless build shows a crash dialog).
 args.invalid_link=False;code=None
 if len(args.links)>1 or (args.links and args.handoff):args.invalid_link=True
 else:
  value=args.handoff or (args.links[0] if args.links else None)
  try:code=parse_pair_link(value) if value else None
  except ValueError:args.invalid_link=True
 if code or args.invalid_link:args.handoff=True
 return args,code

INVALID_LINK_MESSAGE='ClipBot Companion could not use that pairing link. It may be incomplete or expired. Go back to ClipBot, generate a new pairing code and try again, or paste the code on the Companion page.'

INVALID_ORIGIN_MESSAGE='ClipBot Companion could not start because CLIPBOT_SERVICE_ORIGIN is not a valid address. Use an https:// address (or http:// for this computer only), with no path, then open the Companion again.'

def show_notice(message):
 # Windowless builds have no console, so use a native notice on Windows and stay quiet elsewhere.
 if sys.platform!='win32':return
 try:
  import ctypes;ctypes.windll.user32.MessageBoxW(None,message,'ClipBot Companion',0x40)
 except Exception:pass

def show_invalid_link():show_notice(INVALID_LINK_MESSAGE)

def main():
 args,code=parse_launch_args()
 if args.invalid_link:show_invalid_link();return
 try:ORIGIN=configured_origin()
 except ValueError:show_notice(INVALID_ORIGIN_MESSAGE);return
 native=integration();root=native.user_directory()
 from .observability import configure
 configure(root)
 if getattr(sys,'frozen',False):os.environ['PATH']=str(Path(sys._MEIPASS)/'bin')+os.pathsep+os.environ.get('PATH','')
 if args.diagnose or args.diagnose_media:
  import json
  from .prerequisites import prerequisites
  from .transcribe import load_model,transcribe
  model=Path(__file__).parent/'data/models/base';result=prerequisites(model)
  try:
   loaded=load_model(model);result['modelLoads']=True
   if args.diagnose_media:
    segments=transcribe(Path(args.diagnose_media),loaded);result['mediaTranscribes']=True;result['segmentCount']=len(segments)
    if args.diagnose_rolling:
     import subprocess
     from .rolling_buffer import extract
     from .capture import probe
     smoke=root/'diagnostic-buffer';smoke.mkdir(parents=True,exist_ok=True)
     call=subprocess.run([media_tool('ffmpeg'),'-nostdin','-v','error','-y','-i',args.diagnose_media,'-t','80','-map','0:v:0','-map','0:a:0?','-c','copy','-f','segment','-segment_time','5','-reset_timestamps','1',str(smoke/'segment-%08d.mkv')],stderr=subprocess.DEVNULL,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
     if call.returncode:raise RuntimeError('Buffer smoke failed.')
     parts=[];position=0
     for path in sorted(smoke.glob('segment-*.mkv')):
      length=probe(path);parts.append((path,position,position+length));position+=length
     selected=extract(parts,20,60,smoke/'selected',threading.Event());result['rollingClipPasses']=abs(probe(selected)-40)<.8
     for part,a,b in parts:part.unlink(missing_ok=True)
     selected.unlink(missing_ok=True)
    if args.diagnose_preview_candidate:
     from .render import render
     candidate=json.loads(Path(args.diagnose_preview_candidate).read_text(encoding='utf-8'));artifact=render(candidate,Path(args.diagnose_media),segments,Path(args.diagnose_media).parent);result['candidatePreviewPasses']=True;result['verticalReviewPasses']=artifact['framing']=='blurred_fit'
  except Exception:result['modelLoads']=False
  (root/'diagnostics.json').write_text(json.dumps(result),encoding='utf-8');return
 instance=native.SingleInstance()
 if code:save(root/'pair-handoff.bin',ORIGIN,code);code=None
 if not instance.primary:
  if not args.background and not args.handoff:webbrowser.open('http://127.0.0.1:8767/')
  instance.close();return
 if getattr(sys,'frozen',False):os.environ['PATH']=str(Path(sys._MEIPASS)/'bin')+os.pathsep+os.environ.get('PATH','')
 from .local_app import create_local_app
 import uvicorn,pystray
 from PIL import Image,ImageDraw
 app=create_local_app(ORIGIN,root/'jobs');server=uvicorn.Server(uvicorn.Config(app,host='127.0.0.1',port=8767,access_log=False,proxy_headers=False,log_config=None,log_level='critical'))
 thread=threading.Thread(target=server.run,daemon=True);thread.start();stop=threading.Event()
 def handoffs():
  while not stop.wait(1):
   handoff=root/'pair-handoff.bin'
   if not handoff.is_file():continue
   try:
    from .platforms.posix_integration import consume_pair_link
    value=consume_pair_link(root)
    if value:app.state.pair_companion(value);value=None
   except Exception:app.state.worker['message']='Pairing did not finish. Generate a new code in ClipBot.'
 threading.Thread(target=handoffs,daemon=True).start()
 image=Image.new('RGB',(64,64),'#091217');draw=ImageDraw.Draw(image);draw.rounded_rectangle((8,8,56,56),radius=12,fill='#00d9ce');draw.text((22,20),'CB',fill='#091217')
 if sys.platform=='darwin':native.install_url_handler(lambda:app.state.worker.update(message='Pairing did not finish. Generate a new code in ClipBot.'))
 def quit_app(icon,_):stop.set();server.should_exit=True;icon.stop()
 def toggle_start(icon,_):
  try:native.set_startup(not native.startup_enabled());icon.update_menu()
  except Exception:app.state.worker['message']='Startup preference could not be changed.'
 menu=pystray.Menu(pystray.MenuItem('Open ClipBot',lambda *_:webbrowser.open(ORIGIN),default=True),pystray.MenuItem('Connection status',lambda *_:webbrowser.open('http://127.0.0.1:8767/')),pystray.MenuItem('Start with Windows' if sys.platform=='win32' else 'Start when I sign in',toggle_start,checked=lambda _:native.startup_enabled()),pystray.MenuItem('Quit companion',quit_app))
 icon=pystray.Icon('ClipBotCompanion',image,'ClipBot Companion - controlled from your website',menu)
 app.state.tray_icon=icon
 if not args.background and not args.handoff:threading.Timer(2,lambda:webbrowser.open('http://127.0.0.1:8767/')).start()
 try:icon.run()
 finally:stop.set();server.should_exit=True;finish_shutdown(server,thread,instance)
if __name__=='__main__':main()
