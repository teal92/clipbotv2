import {normalizeActivity} from './activity.js';
// Same-origin health checks only; this module never calls Claude or sends API keys.
export async function checkService(fetcher=globalThis.fetch) {
 const controller=new AbortController();
 const timer=setTimeout(()=>controller.abort(),5000);
 try {
  const response=await fetcher('/api/status',{credentials:'same-origin',cache:'no-store',headers:{Accept:'application/json'},signal:controller.signal});
  if(!response.ok) throw Error('unavailable');
  const data=await response.json();
  if(data?.service!=='clipbot'||data.version!==1||typeof data.worker?.connected!=='boolean'||typeof data.davey?.configured!=='boolean'||typeof data.budget?.enforced!=='boolean') throw Error('invalid');
  return {connected:true,workerConnected:data.worker.connected,daveyConfigured:data.davey.configured,budgetEnforced:data.budget.enforced};
 } catch { return {connected:false,workerConnected:false,daveyConfigured:false,budgetEnforced:false}; }
 finally { clearTimeout(timer); }
}

// Explicit connection only. No automatic retries or background calls after leaving Logs.
export function connectActivityFeed(onEntry,onConnection,Source=globalThis.EventSource) {
 const source=new Source('/api/events');
 let closed=false;
 source.onopen=()=>{if(!closed)onConnection(true);};
 source.onmessage=event=>{
  if(closed || typeof event.data!=='string' || event.data.length>8192) return;
  try {
   const data=JSON.parse(event.data);
   const entry=normalizeActivity(data);if(entry)onEntry(entry);
  } catch { /* Invalid events never reach rendering or storage. */ }
 };
 const stop=()=>{if(closed)return;closed=true;source.close();};
 source.onerror=()=>{stop();onConnection(false);};
 return stop;
}
