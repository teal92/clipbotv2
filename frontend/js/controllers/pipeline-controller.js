import {loadProcessingDiagnostics} from './processing-controller.js';
import {handlePublishClick,loadPublishingConnections,invalidateTikTokChoices,getPublishingNotice,publicationFor,PUBLISH_NAMES,handlePublishingBundleChange} from './publishing-controller.js';
import {api,refreshWorkspace,resetSession,getWorkspace} from '../service-state.js';
import {renderPublishing} from '../views/publishing.js';
import {renderClips} from '../views/clips.js';
import {renderProcessing} from '../views/processing.js';
import {repaintDashboardMetrics} from './dashboard-controller.js';
import {renderDashboard} from '../views/dashboard.js';
export {safePreviewUrl} from '../pipeline-utils.js';
let timer=null,expired=()=>{};
export function preservePipelineDisclosures(current,next){
 const states=new Map([...current.querySelectorAll('[data-pipeline-disclosure]')].map(d=>[d.dataset.pipelineDisclosure,d.open]));
 for(const detail of next.querySelectorAll('[data-pipeline-disclosure]'))if(states.has(detail.dataset.pipelineDisclosure))detail.open=states.get(detail.dataset.pipelineDisclosure);
}
export function refreshDeliveryBadges(page){
 for(const row of page.querySelectorAll?.('[data-publish-row]')??[]){
  for(const badge of row.querySelectorAll?.('[data-delivery-platform]')??[]){
   const item=publicationFor(getWorkspace(),row.dataset.publishRow,badge.dataset.deliveryPlatform);if(!item)continue;
   const label=({published:'Published',failed:'Failed',unknown:'Awaiting confirmation',prepared:'Queued',uploading:'Uploading',uploaded:'Confirming',finishing:'Confirming',initializing:'Preparing'})[item.status]??'Awaiting confirmation';
   badge.dataset.deliveryStatus=item.status;const text=PUBLISH_NAMES[item.platform]+': '+label+' ';if(badge.firstChild?.nodeType===3)badge.firstChild.nodeValue=text;else badge.prepend(document.createTextNode(text));if(['published','failed'].includes(item.status))badge.querySelector('[data-pipeline-reconcile]')?.remove();
  }
  const notice=getPublishingNotice(row.dataset.publishRow);if(notice&&!row.dataset.publishBusy){const output=row.querySelector('[data-pipeline-status]');if(output)output.textContent=notice;}
 }
}
export function stopPipeline(){clearInterval(timer);timer=null;}
export async function loadPipeline(root,onExpired=expired){
 const page=root.querySelector('.publishing-page, .clips-page, .processing-page, .dashboard');if(!page)return;
 try{await refreshWorkspace();if(page.matches('.publishing-page')){const links=await loadPublishingConnections();invalidateTikTokChoices(page,links);refreshDeliveryBadges(page);if(page.querySelector('[data-publish-busy], [data-tiktok-fields]:not([hidden])'))return;}if(page.matches('.clips-page')&&page.querySelector('[data-decision-panel]:not([hidden])'))return;if(!page.isConnected||document.activeElement?.closest('form, [data-decision-panel]'))return;
  const disclosures=[...page.querySelectorAll('[data-pipeline-disclosure]')].map(d=>({dataset:{...d.dataset},open:d.open})),disclosureState={querySelectorAll:()=>disclosures};
  const players=[...page.querySelectorAll('[data-clip-video-id]')],parent=page.parentElement,openClips=[...page.querySelectorAll('[data-publish-clip][open]')].map(d=>d.dataset.publishClip);
  page.outerHTML=page.matches('.publishing-page')?renderPublishing():page.matches('.clips-page')?renderClips():page.matches('.processing-page')?renderProcessing():renderDashboard();
  if(parent){preservePipelineDisclosures(disclosureState,parent);repaintDashboardMetrics(parent);if(parent.querySelector('.processing-page'))await loadProcessingDiagnostics(parent);}
  for(const fresh of parent?.querySelectorAll('[data-clip-video-id]')??[]){const old=players.find(p=>p.dataset.clipVideoId===fresh.dataset.clipVideoId&&p.getAttribute('src')===fresh.getAttribute('src'));if(old)fresh.replaceWith(old);}
  for(const detail of parent?.querySelectorAll('[data-publish-clip]')??[])if(openClips.includes(detail.dataset.publishClip))detail.open=true;
 }catch(error){if(error.status===401){stopPipeline();resetSession();onExpired();return;}const output=page.querySelector('[data-pipeline-status]');if(output)output.textContent=error.message;}
}
export function startPipeline(root,onExpired=()=>{}){stopPipeline();expired=onExpired;let pending=false;const poll=async()=>{if(pending)return;pending=true;try{await loadPipeline(root,onExpired);}finally{pending=false;}};timer=setInterval(poll,5000);poll();}
// Legacy editable forms cannot initiate a publication; queue buttons use approved metadata.
export async function handlePipelineSubmit(event){if(event.target.closest('[data-pipeline-publish]'))event.preventDefault();}
export async function handlePipelineClick(event){
 const button=event.target.closest('[data-publish-platform], [data-pipeline-reconcile], [data-pipeline-refresh]');if(!button)return;if(button.dataset.publishPlatform){event.preventDefault?.();const result=await handlePublishClick(button),parent=button.closest('.publishing-page')?.parentElement;if(result?.prepared&&parent)await loadPipeline(parent);return;}button.disabled=true;
 try{if(button.dataset.pipelineReconcile)await api('/api/pipeline/publications/'+encodeURIComponent(button.dataset.pipelineReconcile)+'/reconcile',{method:'POST'});await loadPipeline(button.closest('.publishing-page, .clips-page, .processing-page, .dashboard').parentElement);}
 catch(error){const output=button.closest('.workspace-page')?.querySelector('[data-pipeline-status]');if(output)output.textContent=error.message;}finally{button.disabled=false;}
}
export async function handlePipelineChange(event){handlePublishingBundleChange(event);}
