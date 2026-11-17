import hashlib,json,re,os
from pathlib import Path
from fastapi import HTTPException
from fastapi.responses import StreamingResponse
from starlette.background import BackgroundTask

FILENAMES={'windows-x86_64':'ClipBotCompanionSetup.exe','macos-arm64':'ClipBotCompanion-arm64.dmg','macos-x86_64':'ClipBotCompanion-x86_64.dmg','linux-x86_64':'clipbot-companion-amd64.deb'}

class OwnerInstaller:
 def __init__(self,root,target='windows-x86_64'):
  if target not in FILENAMES:raise ValueError('Unsupported companion platform.')
  folder=Path(root)/'companion'
  if target!='windows-x86_64':folder=folder/'targets'/target
  self.target=target;self.path=folder/FILENAMES[target];self.metadata={'available':False};self.signature=None;self.production_ready=False;self.beta_ready=False
  try:
   if any(p.is_symlink() or (hasattr(p,'is_junction') and p.is_junction()) for p in (self.path,*self.path.parents)):return
   manifest=json.loads(self.path.with_name('manifest.json').read_text(encoding='utf-8-sig'))
   if not isinstance(manifest,dict) or not isinstance(manifest.get('sha256'),str) or not re.fullmatch(r'[a-f0-9]{64}',manifest['sha256']) or not isinstance(manifest.get('version'),str) or not re.fullmatch(r'[A-Za-z0-9._-]{1,40}',manifest['version']) or type(manifest.get('sizeBytes')) is not int or manifest['sizeBytes']<=0:return
   with self.path.open('rb') as stream:
    before=self.identity(os.fstat(stream.fileno()));digest=hashlib.file_digest(stream,'sha256').hexdigest();after=self.identity(os.fstat(stream.fileno()))
   if before!=after or digest!=manifest['sha256'] or after[2]!=manifest['sizeBytes']:return
   if target!='windows-x86_64' and (manifest.get('target')!=target or not isinstance(manifest.get('minimumOS'),str) or not re.fullmatch(r'[A-Za-z0-9 .+_-]{1,80}',manifest['minimumOS'])):return
   self.signature=after
   self.production_ready=manifest.get('channel')=='production' and all(manifest.get(k) is True for k in ('signed','provenanceVerified','cleanMachineAccepted'))
   if target.startswith('macos-') and manifest.get('notarized') is not True:self.production_ready=False
   self.beta_ready=manifest.get('channel')=='beta' and manifest.get('signed') is False and manifest.get('provenanceVerified') is True and manifest.get('cleanInstallPairedAccepted') is True
   self.metadata={'available':True,'url':'/api/companion/download','version':manifest['version'],'sha256':digest,'signed':manifest.get('signed') is True}
   if target!='windows-x86_64':self.metadata.update(target=target,minimumOS=manifest['minimumOS'],url='/api/companion/download?target='+target)
   if manifest.get('releaseKind')=='patch':self.metadata['releaseKind']='patch'
  except (OSError,ValueError,KeyError,TypeError):pass
 @staticmethod
 def identity(stat):return (stat.st_dev,stat.st_ino,stat.st_size,stat.st_mtime_ns)
 def ready(self):
  try:return self.signature==self.identity(self.path.stat())
  except OSError:return False
 def response(self):
  try:stream=self.path.open('rb')
  except OSError:raise HTTPException(503,'Companion download is being prepared. Try again shortly.') from None
  if self.signature!=self.identity(os.fstat(stream.fileno())):
   stream.close();raise HTTPException(503,'Companion download is being prepared. Try again shortly.')
  def chunks():
   try:
    while True:
     if self.signature!=self.identity(os.fstat(stream.fileno())):raise OSError('Installer changed during transfer')
     chunk=stream.read(1024*1024)
     if not chunk:break
     yield chunk
   finally:stream.close()
  return StreamingResponse(chunks(),background=BackgroundTask(stream.close),media_type='application/octet-stream',headers={'Content-Disposition':'attachment; filename="'+FILENAMES[self.target]+'"','Content-Length':str(self.signature[2]),'Cache-Control':'private, no-store','X-Content-Type-Options':'nosniff'})

