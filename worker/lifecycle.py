from .version import VERSION
"""Background lifecycle: transient outages retry, revocation stops permanently."""
class CompanionLifecycle:
 def __init__(self,runtime,processor,client):
  self.runtime=runtime;self.processor=processor;self.client=client;self.failures=0;self.message='Companion ready. Use Start ClipBot on the website.'
 def tick(self):
  try:
   self.runtime.tick();self.processor.tick();self.failures=0;self.message=self.processor.last_error or 'Companion ready. Use Start and Stop on the website.';return 5
  except Exception:
   if not self.client.token:self.shutdown();self.message='Companion access expired or was revoked. Reconnect through ClipBot.';return None
   self.failures+=1
   if self.failures>=3:
    for future,event in list(self.runtime.active.values()):event.set()
   self.message='Connection interrupted. The companion is reconnecting.';return min(30,5*2**min(self.failures-1,3))
 def shutdown(self):self.runtime.close();self.processor.close()

class CompanionHealth:
 def __init__(self,client,slots):self.client=client;self.slots=slots;self.failures=0;self.message='Local processing needs repair. Reinstall the companion.'
 def tick(self):
  try:
   from .platforms.identity import current_target
   self.client.companion_heartbeat({'version':VERSION,'platformTarget':current_target(),'ready':False,'monitoring':False,'acknowledgedRevision':'','hardwareSlots':self.slots,'activeScouts':0,'errorCode':'tools_missing'})
   self.failures=0;return 5
  except Exception:
   if not self.client.token:self.message='Companion access was revoked. Reconnect through ClipBot.';return None
   self.failures+=1;return min(30,5*2**min(self.failures-1,3))
