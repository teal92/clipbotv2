import {api,getAccount,getWorkspace,refreshWorkspace,getSessionGeneration} from '../service-state.js';
import {escapeHtml as e} from '../ui-utils.js';
export const PUBLISH_PLATFORMS=Object.freeze(['tiktok','instagram','facebook']);
export const PUBLISH_NAMES={tiktok:'TikTok',instagram:'Instagram',facebook:'Facebook'};
let connectionScope='',connections=null,attempts=new Map(),notices=new Map(),selectedBundle='';
const busy=new Set();
const scope=()=>{const a=getAccount();return a?.user?.id&&a.csrfToken?getSessionGeneration()+':'+a.user.id+':'+a.csrfToken:'';};
function syncScope(){const key=scope();if(key!==connectionScope){connectionScope=key;connections=null;attempts=new Map();notices=new Map();selectedBundle='';}return key;}
export function renderPublishingBundleDownload(state){
 syncScope();
 const ids=[...new Set((state.publications??state.published??[]).slice().sort((a,b)=>(b.updated??0)-(a.updated??0)).map(item=>item.clipId).filter(id=>typeof id==='string'&&/^[a-f0-9]{32}$/.test(id)))];
 const selected=ids.includes(selectedBundle)?selectedBundle:ids[0];
 return `<div class="publishing-bundle-control" data-publishing-bundle-control>${ids.length?`<label>Clip logs <select data-publishing-bundle-select aria-label="Clip for publishing logs">${ids.map(id=>`<option value="${id}" ${id===selected?'selected':''}>${e(state.ready?.find(c=>c.id===id)?.title??'Archived clip '+id.slice(0,8))}</option>`).join('')}</select></label><a class="btn" data-publishing-bundle-download href="/api/pipeline/publishing-logs/${selected}" download>Download logs bundle</a>`:'<button class="btn" disabled>Download logs bundle</button>'}<small>Social upload attempts, results and errors for the selected clip.${!ids.length?' Available after a publishing attempt.':''}</small></div>`;
}
export function handlePublishingBundleChange(event){
 const select=event.target.closest?.('[data-publishing-bundle-select]');if(!select)return;
 syncScope();const id=select.value;
 if(!/^[a-f0-9]{32}$/.test(id)||(getWorkspace().publications??getWorkspace().published??[]).every(item=>item.clipId!==id))return;
 selectedBundle=id;const link=select.closest('[data-publishing-bundle-control]')?.querySelector('[data-publishing-bundle-download]');
 if(link)link.setAttribute('href','/api/pipeline/publishing-logs/'+id);
}
export function getPublishingNotice(id){syncScope();return notices.get(id)??'';}
export function getPublishingConnections(){syncScope();return connections;}
export async function loadPublishingConnections(){const key=syncScope(),result=await api('/api/connections');if(!key||key!==scope())throw Error('Account changed. Reload this view.');connections=result;return result;}
export function publicationFor(state,clipId,platform){syncScope();return (state.publications??state.published??[]).find(p=>p.clipId===clipId&&p.platform===platform)??attempts.get(clipId+':'+platform);}
export function publishingReason(clip,platform,state,links){
 if(!clip?.artifact||!state.ready?.some(c=>c.id===clip.id)||state.pipelineJobs?.some(j=>j.id===clip.id&&!['ready','publishing','published'].includes(j.stage)))return 'Waiting for a verified rendered clip';
 if(typeof clip.title!=='string'||!clip.title.trim()||clip.title.length>100||typeof clip.caption!=='string'||!clip.caption.trim()||clip.caption.length>2200)return 'Approved title or caption is unavailable';
 const attempt=publicationFor(state,clip.id,platform);if(attempt)return PUBLISH_NAMES[platform]+': '+(attempt.status==='published'?'Published':attempt.status==='failed'?'Needs attention':attempt.status==='unknown'?'Check delivery status':attempt.status.replaceAll('_',' '));
 if(state.workerConnected!==true)return 'Connect your local worker';
 const link=links?.platforms?.find(p=>p.id===platform);
 if(!link?.connected||link.status!=='connected')return 'Connect '+PUBLISH_NAMES[platform];
 if(link.destinationRequired)return 'Choose '+PUBLISH_NAMES[platform]+' destination in Connect Accounts';
 return '';
}
// Preserve the creator shown to the user independently of the polling connection cache.
function creatorFingerprint(info){
 if(typeof info?.creator_username!=='string'||!info.creator_username.trim())throw Error('TikTok creator identity could not be verified. Check your connection before posting.');
 return JSON.stringify([info.creator_username,info.creator_nickname??'',info.privacy_level_options,info.comment_disabled===true,info.duet_disabled===true,info.stitch_disabled===true,info.max_video_post_duration_sec??null]);
}
export function invalidateTikTokChoices(page,links){
 const destination=links?.platforms?.find(p=>p.id==='tiktok');
 for(const fields of page.querySelectorAll?.('[data-tiktok-fields]:not([hidden])')??[]){
  if(!fields.dataset?.creatorFingerprint)continue;
  if(!destination?.connected||destination.status!=='connected'||fields.dataset.destinationName!==destination.accountName){
   fields.dataset.creatorStale='true';fields.querySelector('[name="privacy"]').value='';
   const output=fields.closest?.('[data-publish-row]')?.querySelector('[data-pipeline-status]');
   const message='TikTok destination changed. Press Post TikTok to review the new creator and choose visibility again.';const id=fields.closest?.('[data-publish-row]')?.dataset.publishRow;if(id)notices.set(id,message);if(output)output.textContent=message;
  }
 }
}
export async function handlePublishClick(button){
 const row=button.closest('[data-publish-row]');if(!row||button.disabled)return;
 const key=syncScope(),id=row.dataset.publishRow,lock=key+':'+id,output=row.querySelector('[data-pipeline-status]');
 if(!key||busy.has(lock))return;busy.add(lock);row.dataset.publishBusy='true';
 const buttons=[...row.querySelectorAll('[data-publish-platform]')],disabled=buttons.map(b=>b.disabled);for(const b of buttons)b.disabled=true;
 const guard=()=>{if(scope()!==key||row.isConnected===false)throw Error('Account or view changed. Reload Publishing.');};
 const prepared=[],failed=[];
 const announce=message=>{notices.set(id,message);output.textContent=message;};
 announce('Checking connected destinations…');
 try{
  guard();const clip=getWorkspace().ready?.find(c=>c.id===id);if(!clip)throw Error('This clip is no longer ready in your account.');
  const previous=getPublishingConnections(),links=await loadPublishingConnections();guard();
  const selected=button.dataset.publishPlatform,targets=(selected==='all'?PUBLISH_PLATFORMS:[selected]).filter(p=>PUBLISH_PLATFORMS.includes(p));
  const eligible=targets.filter(p=>!publishingReason(clip,p,getWorkspace(),links));
  if(!eligible.length)throw Error(targets.map(p=>publishingReason(clip,p,getWorkspace(),links)).filter(Boolean).join('. ')||'No eligible destinations.');
  for(const p of eligible){const before=previous?.platforms?.find(x=>x.id===p),after=links.platforms.find(x=>x.id===p);if(before&&before.accountName!==after.accountName)throw Error('Publishing destination changed. Review the updated destination before posting.');}
  let tiktokOptions;
  if(eligible.includes('tiktok')){
   const fields=row.querySelector('[data-tiktok-fields]');
   const info=await api('/api/pipeline/tiktok-settings');guard();
   const fingerprint=creatorFingerprint(info),destinationName=links.platforms.find(p=>p.id==='tiktok')?.accountName??'';
   if(fields.hidden||fields.dataset.accountScope!==key||fields.dataset.creatorFingerprint!==fingerprint||fields.dataset.destinationName!==destinationName||fields.dataset.creatorStale==='true'){
    const changed=!fields.hidden;
    const privacy=fields.querySelector('[name="privacy"]');privacy.replaceChildren(new Option('Choose visibility',''),...info.privacy_level_options.map(v=>new Option(v.replaceAll('_',' ').toLowerCase(),v)));
    fields.querySelector('[data-tiktok-creator]').textContent='TikTok: '+(info.creator_nickname||info.creator_username)+' (@'+info.creator_username+')';
    for(const [name,flag] of [['disableComment','comment_disabled'],['disableDuet','duet_disabled'],['disableStitch','stitch_disabled']]){const input=fields.querySelector('[name="'+name+'"]');input.checked=info[flag]===true;input.disabled=info[flag]===true;}
    fields.dataset.accountScope=key;fields.dataset.creatorFingerprint=fingerprint;fields.dataset.destinationName=destinationName;delete fields.dataset.creatorStale;fields.hidden=false;
    announce((changed?'TikTok creator or settings changed. ':'')+'Choose TikTok visibility, review interaction settings, then press '+(selected==='all'?'Post all':'Post TikTok')+' again.');return;
   }
   const privacy=fields.querySelector('[name="privacy"]');if(!privacy.value)throw Error('Choose TikTok visibility before posting.');
   tiktokOptions={privacy:privacy.value};for(const name of ['disableComment','disableDuet','disableStitch'])tiktokOptions[name]=fields.querySelector('[name="'+name+'"]')?.checked===true;
  }
  for(const platform of eligible){
   guard();const current=getWorkspace().ready?.find(c=>c.id===id);
   if(!current||current.artifact?.sha256!==clip.artifact?.sha256||current.title!==clip.title||current.caption!==clip.caption)throw Error('Approved clip changed. Review Publishing again.');
   if(publishingReason(current,platform,getWorkspace(),links))continue;
   announce('Preparing '+PUBLISH_NAMES[platform]+' upload…');
   attempts.set(id+':'+platform,{clipId:id,platform,status:'unknown'});
   try{const result=await api('/api/pipeline/publish',{method:'POST',body:{clipId:id,platform,options:{title:clip.title,caption:clip.caption,rightsAccepted:true,...(platform==='tiktok'?tiktokOptions:{})}}});guard();if(!result||!/^([a-f0-9]{32})$/.test(result.id??'')||result.clipId!==id||result.platform!==platform||!['initializing','prepared','uploading','uploaded','finishing','unknown','published','failed'].includes(result.status))throw Error('Publication response could not be verified.');attempts.set(id+':'+platform,result);if(['unknown','failed'].includes(result.status))throw Error('Publication needs attention.');prepared.push(PUBLISH_NAMES[platform]);if(platform==='tiktok')row.querySelector('[data-tiktok-fields]').hidden=true;}
   catch(error){guard();failed.push(PUBLISH_NAMES[platform]+': '+error.message+' Check status; no automatic retry was started.');}
  }
  announce([prepared.length?prepared.join(', ')+' upload prepared. Keep your worker running; posting is confirmed by the platform.':'',failed.length?'Needs attention: '+failed.join('; '):''].filter(Boolean).join(' '));
  try{await refreshWorkspace();guard();}catch(error){guard();output.textContent+=' Check status to confirm delivery. '+error.message;}
 return {prepared:prepared.length};
 }catch(error){if(scope()===key&&row.isConnected!==false)announce(error.message);}
 finally{busy.delete(lock);delete row.dataset.publishBusy;if(scope()===key&&row.isConnected!==false)for(const [i,b] of buttons.entries())b.disabled=disabled[i]||!!publicationFor(getWorkspace(),id,b.dataset.publishPlatform);}
}
// The former caption draft form is intentionally absent; keep the delegated import inert.
export function handlePublishingSubmit(){}
