"""Read-only chat cues through the paired service; no platform tokens on disk."""
import time,threading
from urllib.parse import urlencode
from .capture import stream_url

class RelayChatWatcher:
 def __init__(self,client,source,on_message,event):
  stream_url(source);self.client=client;self.source={k:source[k] for k in ('platform','login')};self.on_message=on_message;self.event=event;self.closed=threading.Event();self.status='connecting';self.cursor=0;self.generation=''
 def close(self):self.closed.set();self.status='unavailable'
 def run(self):
  renewed=0
  while not self.event.is_set() and not self.closed.is_set():
   try:
    if time.monotonic()-renewed>=30:
     response=self.client.request('POST','/api/worker/chat/subscribe',self.source);renewed=time.monotonic();self.status=response.get('status','unavailable')
    if self.status!='unavailable':
     response=self.client.request('GET','/api/worker/chat?'+urlencode({**self.source,'cursor':self.cursor,'generation':self.generation}));self.status=response.get('status','unavailable')
     generation=response.get('generation','')
     if generation!=self.generation:self.cursor=0;self.generation=generation
     rows=response.get('messages',[])
     if not isinstance(rows,list) or len(rows)>500:raise ValueError()
     for row in rows:
      if not isinstance(row.get('text'),str) or len(row['text'])>500 or type(row.get('id')) is not int:continue
      if row['id']<=self.cursor:continue
      age=max(0,min(30,time.time()-row.get('created',time.time())));self.on_message(row['text'],time.monotonic()-age);self.cursor=row['id']
   except Exception:self.status='unavailable'
   self.closed.wait(3)
