import {appendActivity} from '../activity.js';
import {checkOnboarding} from './onboarding-controller.js';

import {api,getAccount,resetSession} from '../service-state.js';

import {renderCompanionStatus,renderCompanionSetup,renderCompanionPairing,companionHint} from '../views/companion.js';

import {mountPairingCode} from '../pairing-code.js';
import {COMPANION_PLATFORMS,initialDownload} from '../companion-platform.js';

let lastProblem='';

export function companionUpdateRequired(value){return !!(value.download?.available&&(!value.download.target||!value.platformTarget||value.download.target===value.platformTarget)&&value.companionVersion&&value.companionVersion!==(value.requiredVersion??value.download.version));}

export function createCompanionUpdateNotifier(){
 let shown='';
 return (value,{root=document,signedIn=!!getAccount(),visible=!document.hidden}={})=>{
  if(!signedIn||!visible||!companionUpdateRequired(value))return false;
  const key=String(value.download.version)+'\n'+String(value.download.sha256),dialog=root.querySelector('[data-companion-dialog]');
  if(key===shown||!dialog||root.querySelector('dialog[open]'))return false;
  selectedDownload=null;dialog.innerHTML=renderCompanionSetup(value.download,{reason:'update',version:value.companionVersion});
  dialog.showModal();dialog.scrollTop=0;const heading=dialog.querySelector?.('#companion-title');heading?.setAttribute('tabindex','-1');heading?.focus({preventScroll:true});shown=key;return true;
 };
}

let notifyUpdate=createCompanionUpdateNotifier(),visibilityListener=null;

export function companionStartAction(value){

 const required=value.requiredVersion??value.download?.version;

 if(value.companionVersion&&required&&value.companionVersion!==required)return 'update';

 if(value.state==='offline')return 'connect';

 if(value.errorCode==='tools_missing')return 'repair';

 if(value.state==='attention')return 'blocked';

 return ['ready','running','starting'].includes(value.state)?'start':'wait';

}

function logProblem(value){const message=companionUpdateRequired(value)?'Your companion needs an update. Use Check companion at the top of the page.':companionHint(value);if(message&&message!==lastProblem)appendActivity({level:'error',source:'service',message});lastProblem=message;}

let selectedDownload=null,timer=null,generation=0,status={state:'offline',requestedRunning:false,download:{available:false}},expired=()=>{};

export function getCompanionStatus(){return status;}
export function stopCompanionControls(){selectedDownload=null;if(visibilityListener)document.removeEventListener?.('visibilitychange',visibilityListener);visibilityListener=null;notifyUpdate=createCompanionUpdateNotifier();lastProblem='';generation++;clearTimeout(timer);timer=null;const dialog=document.querySelector('[data-companion-dialog]');dialog?.close();dialog?.replaceChildren();}

export function startCompanionControls(_root,onExpired){stopCompanionControls();status={state:'offline',requestedRunning:false,download:{available:false}};const initial=document.querySelector('[data-companion-controls]');if(initial){initial.innerHTML=renderCompanionStatus(status);delete initial.dataset.companionHtml;}expired=onExpired;visibilityListener=()=>{if(!document.hidden&&!document.querySelector('[data-companion-dialog]')?.open)notifyUpdate=createCompanionUpdateNotifier();};document.addEventListener?.('visibilitychange',visibilityListener);const epoch=generation;const poll=async()=>{try{const next=await api('/api/companion/status');if(epoch!==generation||!getAccount())return;status=next;logProblem(next);notifyUpdate(next);const hint=document.querySelector('[data-companion-header-message]');if(hint&&(next.state==='attention'||hint.dataset.attention)){hint.textContent=companionHint(next);hint.dataset.attention=next.state==='attention'?'yes':'';}const bar=document.querySelector('[data-companion-controls]');if(bar){const html=renderCompanionStatus(status);if(bar.dataset.companionHtml!==html){bar.innerHTML=html;bar.dataset.companionHtml=html;}}}catch(error){if(epoch!==generation)return;if(error.status===401){stopCompanionControls();resetSession();expired();return;}const bar=document.querySelector('[data-companion-controls]');if(bar)bar.innerHTML=renderCompanionStatus({...status,state:'offline'});}if(epoch===generation)timer=setTimeout(poll,3000);};poll();}

export async function handleCompanionClick(event){const button=event.target.closest('[data-companion-action]');if(!button)return;const action=button.dataset.companionAction,dialog=document.querySelector('[data-companion-dialog]');button.disabled=true;

try{if(action==='close'){selectedDownload=null;dialog.close();return;}
if(action==='choose-platform'){
 const target=button.dataset.companionTarget;
 if(!Object.hasOwn(COMPANION_PLATFORMS,target))throw Error('Choose a supported computer.');
 const result=await api('/api/companion/status?target='+encodeURIComponent(target));
 selectedDownload=result.download?.available?result.download:{available:false,target};
 dialog.innerHTML=renderCompanionSetup(selectedDownload);return;
}
if(action==='accept-beta'){
 const download=selectedDownload??status.download;
 if(!download?.unsignedBeta||!download.requiresBetaAcceptance)throw Error('Refresh companion status before downloading.');
 await api('/api/companion/beta-accept',{method:'POST',body:{version:download.version,sha256:download.sha256,acknowledged:true,...(download.target?{target:download.target}:{})}});
 status=await api('/api/companion/status');
 const result=download.target?await api('/api/companion/status?target='+encodeURIComponent(download.target)):status;
 selectedDownload=result.download;
 dialog.innerHTML=renderCompanionSetup(selectedDownload,{reason:companionUpdateRequired(status)?'update':'setup',version:status.companionVersion});return;
}

if(action==='start'||action==='setup'||action==='check'){

 const output=document.querySelector('[data-companion-header-message]');if(output)output.textContent='Checking companion…';

 status=await api('/api/companion/status');

 if(action==='start'&&await checkOnboarding()!=='ready')return;

 const decision=companionStartAction(status);logProblem(status);
 if(action==='setup'||action==='check'||['update','repair','connect'].includes(decision)){selectedDownload=initialDownload(status,globalThis.navigator??{});dialog.innerHTML=renderCompanionSetup(selectedDownload,{reason:action==='setup'?'setup':action==='check'&&decision==='start'?'check':['update','repair','connect'].includes(decision)?decision:'setup',version:status.companionVersion});dialog.showModal();if(output)output.textContent='';return;}

 if(decision!=='start'){const message=decision==='wait'?'The companion is stopping. Wait a moment, then press Start.':companionHint(status);if(output)output.textContent=message;return;}

 if(output)output.textContent='Companion is up to date. Starting ClipBot…';

}

if(action==='start'||action==='stop'){status=await api('/api/companion/control',{method:'POST',body:{running:action==='start'}});document.querySelector('[data-companion-controls]').innerHTML=renderCompanionStatus(status);if(action==='start')api('/api/companion/status').then(logProblem).catch(error=>appendActivity({level:'error',source:'service',message:error.message}));return;}

if(action==='pair'){const result=await api('/api/worker/pairing',{method:'POST'});const host=dialog.querySelector('[data-companion-pair]');host.innerHTML=renderCompanionPairing(result.code);mountPairingCode(host.querySelector('[data-pairing-copy-slot]'),result.code);}}

catch(error){appendActivity({level:'error',source:'service',message:error.message});if(error.status===401){stopCompanionControls();resetSession();expired();return;}const output=dialog?.open?dialog.querySelector('[data-companion-message]'):document.querySelector('[data-companion-header-message]');if(output)output.textContent=error.message;}

finally{button.disabled=false;}}
