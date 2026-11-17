"""Per-user Windows integration. App links are data, never commands."""
import ctypes,hashlib,os,re,sys
from pathlib import Path
from urllib.parse import urlsplit,parse_qs

def user_directory():
 root=Path(os.environ.get('LOCALAPPDATA',str(Path.home()/'AppData/Local')))/'ClipBotCompanion'
 root.mkdir(parents=True,exist_ok=True);return root

def parse_pair_link(value):
 if not isinstance(value,str) or len(value)>256:raise ValueError('Invalid pairing link.')
 p=urlsplit(value);q=parse_qs(p.query,strict_parsing=True)
 if p.scheme!='clipbot-companion' or p.netloc.lower()!='pair' or p.path not in ('','/') or p.fragment or set(q)!={'code'} or len(q['code'])!=1 or not re.fullmatch(r'[A-Za-z0-9_-]{20,100}',q['code'][0]):raise ValueError('Invalid pairing link.')
 return q['code'][0]

class SingleInstance:
 def __init__(self):
  self.api=ctypes.WinDLL('kernel32',use_last_error=True);self.api.CreateMutexW.argtypes=[ctypes.c_void_p,ctypes.c_int,ctypes.c_wchar_p];self.api.CreateMutexW.restype=ctypes.c_void_p;self.api.CloseHandle.argtypes=[ctypes.c_void_p]
  name='Local\\ClipBotCompanion-'+hashlib.sha256(str(user_directory()).encode()).hexdigest()[:24]
  self.handle=self.api.CreateMutexW(None,False,name)
  if not self.handle:raise RuntimeError('Cannot start companion.')
  self.primary=ctypes.get_last_error()!=183
 def close(self):
  if self.handle:self.api.CloseHandle(self.handle);self.handle=None

def startup_enabled():
 import winreg
 try:
  with winreg.OpenKey(winreg.HKEY_CURRENT_USER,r'Software\Microsoft\Windows\CurrentVersion\Run') as key:return bool(winreg.QueryValueEx(key,'ClipBotCompanion')[0])
 except FileNotFoundError:return False

def set_startup(enabled):
 import winreg
 if not getattr(sys,'frozen',False):raise RuntimeError('Startup is available in the installed companion.')
 with winreg.CreateKey(winreg.HKEY_CURRENT_USER,r'Software\Microsoft\Windows\CurrentVersion\Run') as key:
  if enabled:winreg.SetValueEx(key,'ClipBotCompanion',0,winreg.REG_SZ,'"'+sys.executable+'" --background')
  else:
   try:winreg.DeleteValue(key,'ClipBotCompanion')
   except FileNotFoundError:pass
