import {api,getAccount,resetSession} from '../service-state.js';
import {renderDashboardMetrics} from '../dashboard-metrics.js';
let root=null,timer=null,viewsTimer=null,generation=0,metrics=null,owner=null,period='week',accountKey='all',busy=false,error='',expired=()=>{},pending=null,refreshOffset=0;
const user=()=>getAccount()?.user?.id??null;
export function getDashboardMetrics(){return owner===user()?metrics:null;}
export function repaintDashboardMetrics(target=root){
 const panel=target?.querySelector('[data-dashboard-metrics]');
 if(panel)panel.outerHTML=renderDashboardMetrics(getDashboardMetrics(),{period,accountKey,busy,error});
}
export function stopDashboardMetrics(){clearInterval(timer);clearInterval(viewsTimer);timer=null;viewsTimer=null;root=null;generation++;pending=null;metrics=null;owner=null;period='week';accountKey='all';busy=false;error='';refreshOffset=0;}
export async function loadDashboardMetrics(){
 if(!root?.querySelector('.dashboard'))return;
 if(pending)return pending;
 const current=generation,uid=user(),selected=period;
 const operation=(async()=>{try{
  const timezone=Intl.DateTimeFormat().resolvedOptions().timeZone||'UTC';
  const data=await api('/api/dashboard/metrics?'+new URLSearchParams({period:selected,timezone}));
  if(current!==generation||uid!==user())return;
  metrics=data;owner=uid;error='';
  if(accountKey!=='all'&&!metrics.views?.accounts?.some(a=>a.accountKey===accountKey))accountKey='all';
 }catch(cause){if(current!==generation||uid!==user())return;if(cause.status===401){stopDashboardMetrics();resetSession();expired();return;}error=cause.message;}finally{if(current===generation){pending=null;repaintDashboardMetrics();}}})();
 pending=operation;return operation;
}
export function startDashboardMetrics(target,onExpired=()=>{}){stopDashboardMetrics();root=target;expired=onExpired;loadDashboardMetrics().then(()=>refreshViews(true));timer=setInterval(loadDashboardMetrics,30000);viewsTimer=setInterval(()=>refreshViews(true),900000);}
export async function handleDashboardClick(event){
 const button=event.target.closest('[data-dashboard-period], [data-dashboard-refresh-views]');if(!button||!root)return;
 if(button.dataset.dashboardPeriod){period=button.dataset.dashboardPeriod;pending=null;generation++;busy=false;await loadDashboardMetrics();return;}
 await refreshViews(false);
}
async function refreshViews(automatic){
 if(!root||busy)return;const current=generation,uid=user();busy=true;error='';repaintDashboardMetrics();
 try{
  const accounts=(metrics?.views?.accounts??[]).filter(a=>!['permission_required','reconnect_required'].includes(a.status));
  const all=automatic||accountKey==='all';
  const ordered=all?[...accounts.slice(refreshOffset),...accounts.slice(0,refreshOffset)]:accounts.filter(a=>a.accountKey===accountKey);
  const targets=ordered.slice(0,3);
  if(all&&accounts.length)refreshOffset=(refreshOffset+targets.length)%accounts.length;
  // Sequential per-account requests keep provider/API load bounded. Each request is read-only.
  for(const account of targets){if(current!==generation||uid!==user())return;await api('/api/dashboard/views/refresh',{method:'POST',body:{accountKey:account.accountKey}});}
  if(current===generation){pending=null;await loadDashboardMetrics();}
 }catch(cause){if(current===generation&&uid===user()){if(cause.status===401){stopDashboardMetrics();resetSession();expired();return;}error=cause.message;}}
 finally{if(current===generation){busy=false;repaintDashboardMetrics();}}
}
export function handleDashboardChange(event){const input=event.target.closest('[data-dashboard-account]');if(!input||!root)return;accountKey=input.value;repaintDashboardMetrics();}
