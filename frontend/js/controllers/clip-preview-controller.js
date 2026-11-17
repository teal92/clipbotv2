import {localFeedbackUrl} from '../local-feedback.js';
import {getWorkspace,getAccount,getSessionGeneration,refreshWorkspace} from '../service-state.js';
import {safeMediaUrl} from '../pipeline-utils.js';
import {escapeHtml as e} from '../ui-utils.js';
import {candidateMediaUrl,candidateAttributes,renderCandidateDecisionControls,renderSavedDecision} from '../views/clips.js';

let active=null;
export function renderClipPreview(kind,id,state=getWorkspace()){
 const candidate=(kind==='candidate'?state.candidates:kind==='ready'?state.ready:[])?.find(c=>c.id===id);
 if(!candidate)return null;
 let media='';try{media=kind==='candidate'?candidateMediaUrl(candidate):safeMediaUrl(candidate.previewUrl);}catch{}
 const review=state.reviews?.find(r=>r.candidate?.id===id);
 const controls=kind==='candidate'?(review?renderSavedDecision(review.user_feedback.decision,review):renderCandidateDecisionControls().replace('data-clip-action="approve"',media?'data-clip-action="approve"':'data-clip-action="approve" disabled title="Wait for the captioned preview"')):'';
 return `<div class="clip-preview-heading"><div><span class="eyebrow">${kind==='candidate'?'REVIEW CLIP':'APPROVED CLIP'}</span><h2 id="clip-preview-title">${e(candidate.title??candidate.creator??'Clip preview')}</h2></div><button type="button" class="btn" data-close-clip-preview aria-label="Close clip preview">Close preview</button></div><article class="${kind==='candidate'?'candidate-card ':''}clip-preview-content" ${kind==='candidate'?candidateAttributes(candidate):''}><div class="clip-preview-media">${media?`<video class="mobile-clip-player" data-clip-video-id="${e(id)}" controls playsinline preload="metadata" autoplay src="${e(media)}" aria-label="Clip from ${e(candidate.creator??'creator')}"></video>`:''}<p data-clip-preview-status role="status" aria-live="polite">${media?'': 'Local preview is unavailable. Keep the companion running and reopen this clip when it is ready.'}</p></div><div class="clip-preview-review"><p>${e(candidate.creator??'')} · ${e(candidate.platform??'')} · ${e(candidate.duration??(Number.isFinite(candidate.artifact?.duration)?Math.round(candidate.artifact.duration)+' sec':''))}</p>${kind==='candidate'?`<p>Davey score: ${e(candidate.score??'Unscored')}</p><p data-davey-reason>${e(candidate.rationale??'')}</p>${!review&&media?`<div class="clip-basic-editor"><h3>Edit this clip</h3><label>Title<input data-clip-edit-title maxlength="100" value="${e(candidate.title??'')}" required></label><label>Description<textarea data-clip-edit-description maxlength="1000" rows="3">${e(candidate.caption??'')}</textarea></label><div class="clip-trim-fields"><label>Start (seconds)<input data-clip-edit-start type="number" min="0" max="${Math.max(0,(candidate.end??0)-(candidate.start??0))}" step="0.1" value="0"></label><label>End (seconds)<input data-clip-edit-end type="number" min="15" max="${Math.max(15,(candidate.end??0)-(candidate.start??0))}" step="0.1" value="${Math.max(15,(candidate.end??0)-(candidate.start??0))}"></label></div><small>Keep 15–60 seconds within this clip. Captions and mobile framing are preserved.</small><button class="btn approve" data-clip-action="apply-edits-approve">Apply edits and approve</button><p data-clip-edit-status role="status"></p></div>`:''}${controls}<div data-decision-panel hidden></div>`:`<p class="clip-preview-caption">${e(candidate.caption??'Approved caption unavailable')}</p>`}</div></article>`;
}
export function closeClipPreview({restoreFocus=true}={}){
 if(!active)return;
 const {dialog,opener,guardTimer}=active;active=null;clearInterval(guardTimer);
 const video=dialog.querySelector('video');if(video){video.pause();video.removeAttribute('src');video.load();}
 if(dialog.open)dialog.close();dialog.remove();
 if(restoreFocus&&opener?.isConnected)opener.focus();
}
export function handleClipPreviewClick(event){
 if(event.target.closest('[data-close-clip-preview]')){closeClipPreview();return true;}
 const button=event.target.closest('[data-clip-preview]');if(!button||button.disabled)return false;
 event.preventDefault();
 const generation=getSessionGeneration(),userId=getAccount()?.user?.id;
 if(!userId)return true;
 const kind=button.dataset.previewKind,id=button.dataset.clipPreview,markup=renderClipPreview(kind,id);
 if(!markup)return true;
 closeClipPreview({restoreFocus:false});
 const dialog=document.createElement('dialog');dialog.className='clip-preview-dialog workspace-page';dialog.setAttribute('aria-labelledby','clip-preview-title');dialog.dataset.clipPreviewDialog='';dialog.innerHTML=markup;
 document.body.appendChild(dialog);
 active={dialog,opener:button,guardTimer:setInterval(()=>{if(generation!==getSessionGeneration()||userId!==getAccount()?.user?.id)closeClipPreview({restoreFocus:false});},250)};
 dialog.addEventListener('cancel',event=>{event.preventDefault();closeClipPreview();});
 dialog.addEventListener('close',()=>closeClipPreview());
 dialog.addEventListener('click',event=>{if(event.target===dialog){const box=dialog.getBoundingClientRect();if(event.clientX<box.left||event.clientX>box.right||event.clientY<box.top||event.clientY>box.bottom)closeClipPreview();}});
 const video=dialog.querySelector('video'),status=dialog.querySelector('[data-clip-preview-status]');
 video?.addEventListener('error',()=>{if(active?.dialog===dialog)status.textContent='The local preview could not be loaded. Keep the companion running, then close and reopen this clip to use its latest preview.';});
 video?.addEventListener('playing',()=>{if(active?.dialog===dialog)status.textContent='';});
 dialog.showModal();
 if(button.hasAttribute('data-preview-review'))dialog.querySelector('[data-clip-action="re-review"]')?.click();
 video?.play()?.catch(()=>{if(active?.dialog===dialog&&video.error===null)status.textContent='Press play to watch this clip.';});
 return true;
}

export function resetPreviewTrim(card,candidate){
 const duration=candidate.end-candidate.start;
 const start=card.querySelector('[data-clip-edit-start]'),end=card.querySelector('[data-clip-edit-end]');
 start.value='0';start.max=String(duration);end.value=String(duration);end.max=String(duration);
}

export async function applyPreviewEdits(card){
 const id=card.dataset.candidateId,owner=getAccount()?.user?.id,generation=getSessionGeneration(),candidate=getWorkspace().candidates?.find(c=>c.id===id);
 if(!candidate||!owner)throw Error('Reopen this clip in your current account.');
 const title=card.querySelector('[data-clip-edit-title]').value.trim(),description=card.querySelector('[data-clip-edit-description]').value;
 const left=Number(card.querySelector('[data-clip-edit-start]').value),right=Number(card.querySelector('[data-clip-edit-end]').value),duration=candidate.end-candidate.start;
 if(!title||title.length>100||!description.trim()||description.length>1000||![left,right,duration].every(Number.isFinite)||left<0||right>duration||right-left<15||right-left>60)throw Error('Use a title and a 15–60 second trim within this clip.');
 if(title===candidate.title&&description===(candidate.caption??'')&&left===0&&right===duration)return;
 const base=localFeedbackUrl(candidate.previewUrl)+'/edit';
 const guard=()=>{if(generation!==getSessionGeneration()||owner!==getAccount()?.user?.id||!card.isConnected)throw Error('The preview closed or your account changed. Reopen the clip to check its edits.');};
 const request=async(method,body)=>{guard();const response=await fetch(base,{method,mode:'cors',credentials:'omit',cache:'no-store',redirect:'error',referrerPolicy:'no-referrer',signal:AbortSignal.timeout(15000),headers:{Accept:'application/json',...(body?{'Content-Type':'application/json'}:{})},...(body?{body:JSON.stringify(body)}:{})});guard();const data=await response.json();if(!response.ok||data.ok!==true)throw Error(typeof data.detail==='string'?data.detail:'Editing requires the updated companion. No approval was saved.');return data;};
 await request('POST',{userId:owner,title,description,start:candidate.start+left,end:candidate.start+right});
 const output=card.querySelector('[data-clip-edit-status]');output.textContent='Applying edits on your computer…';
 for(let i=0;i<330;i++){
  await new Promise(resolve=>setTimeout(resolve,1000));const result=await request('GET');
  if(result.status==='failed')throw Error('Edits could not be rendered. Your previous clip is retained; no approval was saved.');
  if(result.status==='complete'){
   await refreshWorkspace();guard();const current=getWorkspace().candidates.find(c=>c.id===id);if(!current)throw Error('Updated clip is unavailable. Reopen Clips.');
   card.querySelector('video').src=candidateMediaUrl(current);card.dataset.duration=current.duration;
   card.querySelector('[data-clip-edit-title]').value=current.title;card.querySelector('[data-clip-edit-description]').value=current.caption??'';
   resetPreviewTrim(card,current);
   output.textContent='Edits saved. Tell Davey why you are approving.';return;
  }
 }
 throw Error('Editing is taking longer than expected. Reopen the clip before approving.');
}
