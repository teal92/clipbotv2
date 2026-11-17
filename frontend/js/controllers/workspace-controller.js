import {mountPairingCode} from '../pairing-code.js';
import {api,getAccount} from '../service-state.js';
import { saveSettings, DEFAULT_SETTINGS } from '../settings-state.js';
import { savePlanInterest,saveCustomPlan,calculateCustomPrice,CUSTOM_LIMITS } from '../subscription-plans.js';
import { savePreferences } from '../davey/learning.js';
import { appendActivity, appendActivities, clearActivity, filterActivity, getActivity } from '../activity.js';
import { renderLogEntries, renderSessionBundles } from '../views/logs.js';
import { checkService, connectActivityFeed } from '../runtime.js';

let stopFeed=null,logTimer=null,logCursor=0,logEpoch=0,logPending=null;
let pricingNoticeShown=false;
export function stopWorkspaceActivity(){logEpoch++;clearInterval(logTimer);logTimer=null;logCursor=0;logPending=null;if(stopFeed)stopFeed();stopFeed=null;}
export function startLogs(root){
 stopWorkspaceActivity();const page=root.querySelector?.('.logs-page');if(!page)return;
 refreshLogs(page);logTimer=setInterval(()=>{if(page.isConnected===false){stopWorkspaceActivity();return;}refreshLogs(page);},5000);
}
export async function refreshLogs(page){
 if(!page||page.isConnected===false||logPending)return;
 const generation=logEpoch,uid=getAccount()?.user?.id,request={};logPending=request;
 try{
  const result=await api('/api/logs?after='+logCursor);
  if(generation!==logEpoch||uid!==getAccount()?.user?.id||page.isConnected===false)return;
  if(!Array.isArray(result?.events)||!Number.isSafeInteger(result.cursor)||result.cursor<0)throw Error('Invalid server activity response.');
  const saved=appendActivities(result.events);if(!saved.ok)throw Error(saved.error);
  logCursor=result.cursor;showLogs(page);
  const sessionOutput=page.querySelector('[data-debug-sessions]');
  if(sessionOutput){
   try{
    const bundles=await api('/api/logs/sessions');
    if(generation===logEpoch&&uid===getAccount()?.user?.id&&page.isConnected!==false){
     const html=renderSessionBundles(bundles?.sessions);
     if(sessionOutput.innerHTML!==html)sessionOutput.innerHTML=html;
    }
   }catch{if(generation===logEpoch&&uid===getAccount()?.user?.id&&page.isConnected!==false)sessionOutput.textContent='Session bundles could not be loaded. Refresh to try again.';}
  }
 status(page,'Live pipeline activity updated. Refreshes every five seconds.');
 }catch(error){if(generation!==logEpoch||uid!==getAccount()?.user?.id||page.isConnected===false)return;status(page,'Could not refresh server activity: '+error.message);}
 finally{if(logPending===request)logPending=null;}
}

function status(page,message) { const output=page.querySelector('[data-workspace-status]'); if(output) output.textContent=message; }
function showLogs(page) {
 const output=page.querySelector('[data-log-entries]');
 if(!output) return;
 const expanded=new Set([...(output.querySelectorAll?.('details[open]')??[])].map(detail=>detail.dataset.logId));
 const html=renderLogEntries(filterActivity(getActivity(),{level:page.querySelector('[data-log-level]')?.value??'all',source:page.querySelector('[data-log-source]')?.value??'all',search:page.querySelector('[data-log-search]')?.value??''}));
 if(output.innerHTML===html)return;output.innerHTML=html;
 for(const detail of output.querySelectorAll?.('details[data-log-id]')??[])if(expanded.has(detail.dataset.logId))detail.open=true;
}
export async function handleWorkspaceSubmit(event) {
 const report=event.target.closest('[data-report-form]');
 if(report?.dataset?.reportForm!==undefined){
  event.preventDefault();const output=report.querySelector('[data-report-status]'),button=report.querySelector('[type="submit"]');
  if(button.disabled)return;
  button.disabled=true;output.textContent='Submitting your reportâ€¦';
  try{const receipt=await api('/api/reports',{method:'POST',body:Object.fromEntries(new FormData(report))});report.reset();report.querySelector('[data-bug-fields]').hidden=false;for(const name of ['steps','expected'])report.elements[name].required=true;const delivery=receipt.status==='Queued'?'Queued for email delivery to the support team.':receipt.status==='Accepted by mail server'?'Accepted by the support mail server.':receipt.status==='Delivery unknown'?'Delivery could not be confirmed; saved for team review.':'Saved for team review. Email delivery is not configured.';output.textContent=`Report received. Reference: ${receipt.reference}. ${delivery}`;}
  catch(error){output.textContent=error.message;}
  finally{button.disabled=false;}
  return;
 }

 const form=event.target.closest('[data-workspace-form]');
 if(!form) return;
 event.preventDefault();
 const field=name=>form.elements[name].value;
 const result=form.dataset.workspaceForm==='settings'
 ? saveSettings({usagePreset:field('usagePreset'),mode:field('mode')})
 : form.dataset.workspaceForm==='plan-interest' ? savePlanInterest(field('proposedPlan'))
 : form.dataset.workspaceForm==='custom-plan' ? saveCustomPlan(Object.fromEntries(Object.keys(CUSTOM_LIMITS).map(name=>[name,field(name)===''?null:Number(field(name))])))
 : savePreferences({contentFocus:field('contentFocus'),avoidTopics:field('avoidTopics')});
 const source=form.dataset.workspaceForm==='settings'?'settings':'davey';
 const page=form.closest('.workspace-page');
 status(form,result.ok?(form.dataset.workspaceForm==='plan-interest'?'Plan selection saved. No subscription was purchased.':form.dataset.workspaceForm==='custom-plan'?'Capacity selection saved. Review the subscription quote to continue.':'Preferences saved on this browser. Server synchronization is still required.'):result.error);
 if(!result.ok) appendActivity({level:'error',source:'settings',message:result.error});
 if(result.ok) appendActivity({source,message:source==='settings'?'Agent configuration draft saved. AI remains inactive.':'Content preferences saved locally. Not sent to Claude.'});
}
export function handleWorkspaceInput(event) {
 const report=event.target.closest('[data-report-form]');
 if(report&&event.target.name==='kind'){const bug=event.target.value==='bug';report.querySelector('[data-bug-fields]').hidden=!bug;for(const name of ['steps','expected'])report.elements[name].required=bug;return;}

 const settings=event.target.closest('.settings-page,.account-page');
 if(settings && event.target.matches('[name="proposedPlan"]')){
  settings.querySelector('[data-custom-plan]').hidden=event.target.value!=='custom';
 }
 if(settings && event.target.matches('[data-custom-quantity]')){
  const form=event.target.closest('form');
  const config=Object.fromEntries(Object.keys(CUSTOM_LIMITS).map(name=>[name,Number(form.elements[name].value)]));
  const quote=calculateCustomPrice(config);
  if(!quote)return;
  for(const [name,value] of Object.entries(config))form.querySelector(`[data-custom-value="${name}"]`).textContent=value;
  form.querySelector('[data-custom-price]').textContent=`$${quote.monthlyPrice}/month`;
  form.querySelector('[data-custom-summary]').textContent=`${config.dailyReviews} reviews/day Â· ${quote.monthlyReviews.toLocaleString()} reviews in a 31-day month Â· No ClipBot posting cap`;
  form.querySelector('[data-scout-warning]').textContent=config.scouts>24?'High hardware load: more than 24 scouts can strain CPU, memory, disk and internet bandwidth and may cause crashes. Reduce scouts if performance worsens.':'More scouts increase CPU, memory, disk and internet use on your hardware. Excessive monitoring can cause slowdowns or crashes. Start low and increase after checking your system.';
 }
 const page=event.target.closest('.logs-page');
 if(page && event.target.matches('[data-log-search], [data-log-source], [data-log-level]')) showLogs(page);
}
export function switchSettingsTab(button) {
 const page=button.closest('.settings-page');
 if(!page || !['general','billing'].includes(button.dataset.settingsTab))return;
 page.querySelectorAll('[data-settings-tab]').forEach(tab=>{
  const selected=tab===button;
  tab.classList.toggle('active',selected);
  tab.setAttribute('aria-selected',String(selected));
 });
 page.querySelectorAll('[data-settings-panel]').forEach(panel=>{panel.hidden=panel.dataset.settingsPanel!==button.dataset.settingsTab;});
 if(button.dataset.settingsTab==='billing'&&!pricingNoticeShown){
  const notice=page.querySelector?.('[data-pricing-notice]');
  if(notice?.showModal){notice.showModal();pricingNoticeShown=true;}
 }
}
export async function handleWorkspaceClick(event) {
 const tab=event.target.closest('[data-settings-tab]');
 if(tab){switchSettingsTab(tab);return;}
 const button=event.target.closest('[data-workspace-action]');
 const page=button?.closest('.workspace-page');
 if(!page) return;
 const action=button.dataset.workspaceAction;
 if(action==='pair-worker'||action==='revoke-worker'){
  const output=page.querySelector('[data-worker-status]');button.disabled=true;
  try{const result=await api(action==='pair-worker'?'/api/worker/pairing':'/api/worker/revoke',{method:'POST'});if(action==='pair-worker')mountPairingCode(output,result.code);else output.textContent='Worker access revoked. Any existing connection will stop.';}
  catch(error){output.textContent=error.message;}
  finally{button.disabled=false;}
  return;
 }
 if(action==='refresh-logs'){button.disabled=true;try{await refreshLogs(page);}finally{button.disabled=false;}return;}
 if(action==='clear-logs') {
  // Explicit second step protects local diagnostics from accidental deletion.
  if(button.dataset.confirm!=='yes') {button.dataset.confirm='yes';button.textContent='Confirm Clear';status(page,'Click Confirm Clear to remove only this browserâ€™s activity history.');return;}
  const result=clearActivity();
  button.dataset.confirm='';button.textContent='Clear Browser Logs';
  status(page,result.ok?'Browser logs cleared. Server logs are unaffected.':result.error);showLogs(page);return;
 }
 if(action==='reset-settings') {
  const form=page.querySelector('[data-workspace-form="settings"]');
  for(const name of ['usagePreset','mode']) form.elements[name].value=DEFAULT_SETTINGS[name];
  status(page,'Paused preset selected. Save Preferences to keep it.');return;
 }
 if(action==='connect-feed') {
  const output=page.querySelector('[data-feed-status]');
  if(stopFeed) {stopWorkspaceActivity();button.textContent='Connect Error Feed';output.textContent='Live feed disconnected.';return;}
  button.disabled=true;output.textContent='Checking service before connecting...';
  const service=await checkService();
  if(page.isConnected===false) {button.disabled=false;return;}
  button.disabled=false;
  if(!service.connected) {output.textContent='Cannot reach the server. Error feed was not started.';appendActivity({level:'error',source:'service',message:'The server could not be reached while connecting the error feed.'});showLogs(page);return;}
  try {
   output.textContent='Connecting to worker events...';
   button.textContent='Disconnect Error Feed';
   stopFeed=connectActivityFeed(entry=>{
    const result=appendActivity(entry);
    if(!result.ok) {status(page,result.error);stopWorkspaceActivity();button.textContent='Connect Error Feed';output.textContent='Feed stopped because logs could not be saved.';return;}
    showLogs(page);
   },connected=>{
    output.textContent=connected?'Live worker feed connected.':'Live feed disconnected. Click Connect Error Feed to retry.';
    if(!connected){stopFeed=null;button.textContent='Connect Error Feed';appendActivity({level:'error',source:'service',message:'The live error feed disconnected.'});showLogs(page);}
   });
  } catch {stopWorkspaceActivity();button.textContent='Connect Error Feed';output.textContent='Live events are unavailable in this browser.';}
  return;
 }
 if(action==='check-service') {
  const output=page.querySelector('[data-service-status]');
  button.disabled=true;output.textContent='Checking service...';
  const service=await checkService();
  const message=service.connected?`Service connected. Worker: ${service.workerConnected?'connected':'offline'}. Claude: ${service.daveyConfigured?'configured':'not configured'}. Server budget enforcement: ${service.budgetEnforced?'enabled':'missing'}. This check does not start AI.`:'Cannot reach the server. Check your connection and try again.';
  output.textContent=message;button.disabled=false;
  appendActivity({source:'service',level:service.connected?'info':'error',message});
  showLogs(page);
 }
}




