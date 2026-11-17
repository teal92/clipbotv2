import {saveStreamSettings} from '../stream-settings.js';
import {readDaveyProgression} from '../davey/progression.js';
import {loadTriggerSettings,requestManualTrigger,readTriggerSettings} from './trigger-controller.js';
import {api,getAccount,getWorkspace,refreshWorkspace,resetSession} from '../service-state.js';
import {appendActivity} from '../activity.js';
import {renderStreamers} from '../views/streamers.js';
let snapshot=null,rows=[],categories=[],testStatus=null,scope=null,timer=null,busy=0,epoch=0,expired=()=>{},boards={twitch:{tab:'streams'},kick:{tab:'streams'}},lastDirectory=0;
export function createCategoryCoverageLoader(read=api,clock=Date.now){
 const cache=new Map(),pending=new Map();
 return async(owner,platform,items)=>{
  const ids=items.slice(0,10).map(c=>c.id),key=JSON.stringify([owner,platform,ids]);
  if(!ids.length)return {sources:[],errors:{}};
  const old=cache.get(key);if(old&&clock()-old.time<30000)return old.value;
  if(pending.has(key))return pending.get(key);
  const request=(async()=>{
   let value;
   try{const result=await read('/api/scouts/category-coverage?'+new URLSearchParams({platform,categories:ids.join(',')}));value={sources:result.sources??[],errors:result.errors??{},stale:false};}
   catch(error){if(error.status===401)throw error;value={sources:old?.value.sources??[],errors:old?.value.errors??{},stale:true,error:error.message};}
   cache.set(key,{time:clock(),value});while(cache.size>8)cache.delete(cache.keys().next().value);return value;
  })();pending.set(key,request);try{return await request;}finally{pending.delete(key);}
 };
}
let coverageLoader=createCategoryCoverageLoader();
export function currentDraft(baseline,inputs){return baseline&&inputs.some(c=>String(c.value)!==String(baseline[c.name]))?Object.fromEntries(inputs.map(c=>[c.name,c.value])):null;}
export function directoryItem(items,platform,id,kind='login'){return items.find(v=>v.platform===platform&&v[kind]===id);}
export function priorityLookupNames(platform,configuration,sources=[],monitors=[]){
 return [...new Set([...(configuration.forced??[]),...monitors,...sources].filter(v=>v.platform===platform).map(v=>v.login))].slice(0,65);
}
export function updateSelection(config,kind,item,limits,{addOnly=false}={}){
 if(!['forced','favorites','categories','forcedCategories'].includes(kind))throw Error('Choose a supported scout preference.');
 const next=structuredClone(config),identity=['categories','forcedCategories'].includes(kind)?'id':'login';next[kind]??=[];
 const index=next[kind].findIndex(v=>v.platform===item.platform&&v[identity]===item[identity]);
 if(index>=0){if(addOnly)return next;next[kind].splice(index,1);}else next[kind].push(identity==='id'?{platform:item.platform,id:item.id,name:item.name}:{platform:item.platform,login:item.login});
 const maximum=['forced','forcedCategories'].includes(kind)?next.slots:limits[kind];
 if(next[kind].length>maximum||next.forced.length+(next.forcedCategories?.length??0)>next.slots)throw Error('This selection exceeds your current plan or scout slots.');
 return next;
}
export function stopScouts(){epoch++;clearInterval(timer);timer=null;}
export function reconcilePreviewCard(old,card){const image=card.querySelector('.scout-snapshot');old.querySelector('.scout-snapshot').replaceWith(image);old.querySelector('.scout-tile-stats')?.replaceWith(card.querySelector('.scout-tile-stats'));old.querySelector('.scout-interaction')?.replaceWith(card.querySelector('.scout-interaction'));old.querySelector('.scout-cue-status')?.replaceWith(card.querySelector('.scout-cue-status'));const button=old.querySelector('[data-scout-action="manual"]'),freshButton=card.querySelector('[data-scout-action="manual"]');if(button&&freshButton)button.disabled=freshButton.disabled;old.className=card.className+(old.querySelector('details')?.open?' scout-live-expanded':'');}
export function preserveTriggerEditor(current,next,replace=false){
 if(replace)return;
 const editor=current.querySelector('[data-stream-settings]')??current.querySelector('[data-scout-triggers]'),replacement=next.querySelector('[data-stream-settings]')??next.querySelector('[data-scout-triggers]');
 if(editor&&replacement)replacement.replaceWith(editor);
}
export function preserveFavoriteEditors(current,next){
 for(const form of current.querySelectorAll?.('[data-favorite-entry]')??[]){
  next.querySelector(`[data-favorite-entry="${form.dataset.favoriteEntry}"][data-platform="${form.dataset.platform}"]`)?.replaceWith(form);
 }
}
function paint(page,replaceEditor=false,forceRefresh=false){
 if(!page?.isConnected)return;
 const triggerForm=page.querySelector('[data-scout-triggers]');const triggerDraft=triggerForm&&JSON.stringify(readTriggerSettings(triggerForm))!==JSON.stringify(boards.triggers);if(triggerDraft)boards.triggerDraft=readTriggerSettings(triggerForm);
 const html=renderStreamers(snapshot,rows,categories,testStatus,boards,page.dataset.scoutView??'streamers');
 if(!replaceEditor&&!forceRefresh&&(page.querySelector('.scout-preview-grid details[open]')||document.activeElement?.closest('.streamers-page input, .streamers-page select, .streamers-page textarea'))){
  // Keep mounted players alive: replacing their ancestors resets playback.
  const next=document.createElement('div');next.innerHTML=html;
  page.querySelector('[data-scout-status]').textContent=next.querySelector('[data-scout-status]').textContent;const feedback=page.querySelector('[data-scout-controls-status]');if(feedback)feedback.textContent=next.querySelector('[data-scout-controls-status]').textContent;
  const coverage=page.querySelector('.scout-category-coverage');if(coverage)coverage.replaceWith(next.querySelector('.scout-category-coverage'));
  for(const table of page.querySelectorAll('[data-monitor-table]'))table.innerHTML=next.querySelector(`[data-monitor-table="${table.dataset.monitorTable}"]`).innerHTML;
  const overview=page.querySelector('.scout-overview');if(overview)overview.replaceWith(next.querySelector('.scout-overview'));
  const grid=page.querySelector('.scout-preview-grid'),fresh=[...next.querySelectorAll('[data-preview-key]')];
  for(const card of (grid?.querySelectorAll('[data-preview-key]')??[]))if(!fresh.some(c=>c.dataset.previewKey===card.dataset.previewKey))card.remove();
  for(const card of fresh){const old=[...(grid?.querySelectorAll('[data-preview-key]')??[])].find(c=>c.dataset.previewKey===card.dataset.previewKey);if(!old&&grid)grid.append(card);else{reconcilePreviewCard(old,card);}}
  const toggle=page.querySelector('[data-scout-action="toggle"]'),newToggle=next.querySelector('[data-scout-action="toggle"]');if(toggle&&newToggle){toggle.textContent=newToggle.textContent;toggle.disabled=newToggle.disabled;}
  return;
 }
 // Polls update surrounding status without resetting the live phrase editor.
 const next=document.createElement('div');next.innerHTML=html;
 preserveTriggerEditor(page,next,replaceEditor);preserveFavoriteEditors(page,next);page.replaceWith(next.firstElementChild);
}
function failure(error,page){appendActivity({level:'error',source:'service',message:error.message});boards.notice=error.message;for(const output of page?.querySelectorAll('[data-scout-status], [data-scout-controls-status]')??[])output.textContent=error.message;if(error.status===401){stopScouts();resetSession();expired();}}
async function directory(platform,query='',kind=null){
 const target=kind??'streams';let result;
 if(target==='categories')result=(await api('/api/scouts/categories?'+new URLSearchParams({platform,query}))).categories;
 else result=(await api('/api/scouts/discover?'+new URLSearchParams({platform,logins:query.trim()}))).sources;
 return {platform,target,result};
}
function applyDirectory({platform,target,result}){if(target==='categories')categories=[...categories.filter(v=>v.platform!==platform),...result];else rows=[...rows.filter(v=>v.platform!==platform),...result.sort((a,b)=>(b.viewers??0)-(a.viewers??0))];boards[platform].error='';}
export async function loadScouts(root){
 const page=root.querySelector('.streamers-page');if(!page)return;const requestEpoch=epoch;
 const baseline=snapshot&&getAccount()?.user?.id===scope?{slots:snapshot.configuration.slots,...snapshot.controls}:null;

 try{
  const uid=getAccount()?.user?.id;if(uid!==scope){scope=uid;coverageLoader=createCategoryCoverageLoader();rows=[];categories=[];snapshot=null;boards={twitch:{tab:'streams'},kick:{tab:'streams'}};lastDirectory=0;}
  const result=await Promise.all([api('/api/scouts'),refreshWorkspace(),api('/api/companion/status'),loadTriggerSettings()]);if(requestEpoch!==epoch||uid!==getAccount()?.user?.id)return;
  snapshot={...result[0],companion:result[2]};testStatus=null;boards.triggers=result[3];if(JSON.stringify(boards.triggerDraft)===JSON.stringify(boards.triggers))delete boards.triggerDraft;
  if(Date.now()-lastDirectory>30000){lastDirectory=Date.now();const requests=await Promise.allSettled(['twitch','kick'].flatMap(platform=>['streams','categories'].map(kind=>directory(platform,'',kind))));if(requestEpoch!==epoch)return;requests.forEach((value,index)=>{if(value.status==='fulfilled')applyDirectory(value.value);else boards[index<2?'twitch':'kick'].error=value.reason.message;});const activeRequests=await Promise.allSettled(['twitch','kick'].map(platform=>{const names=priorityLookupNames(platform,snapshot.configuration,getWorkspace().sources,snapshot.companion?.monitoredSources);return names.length?directory(platform,names.join(','),'streams'):Promise.resolve(null);}));if(requestEpoch!==epoch)return;for(const value of activeRequests)if(value.status==='fulfilled'&&value.value){for(const item of value.value.result){const i=rows.findIndex(r=>r.platform===item.platform&&r.login===item.login);if(i<0)rows.push(item);else rows[i]=item;}}}
  const coverage=await Promise.all(['twitch','kick'].map(platform=>coverageLoader(uid,platform,categories.filter(c=>c.platform===platform))));if(requestEpoch!==epoch||uid!==getAccount()?.user?.id)return;
  boards.coverageRows=coverage.flatMap(value=>value.sources);boards.coverageErrors={};for(const [index,platform] of ['twitch','kick'].entries()){const value=coverage[index];if(value.stale)boards.coverageErrors[platform]=value.error+' Showing last known category coverage.';for(const [id,error] of Object.entries(value.errors))boards.coverageErrors[platform+':'+id]=error;}
  const currentPage=root.querySelector('.streamers-page');const inputs=[...(currentPage?.querySelectorAll('[data-scout-controls] select')??[])];const draft=currentDraft(baseline,inputs);paint(currentPage);if(draft){const current=root.querySelector('.streamers-page');for(const [name,value] of Object.entries(draft)){const control=current?.querySelector(`[name="${name}"]`);if(control)control.value=value;}}
 }catch(error){failure(error,page);}
}
export function startScouts(root,onExpired=()=>{}){stopScouts();expired=onExpired;loadScouts(root);timer=setInterval(()=>{if(!busy&&root.querySelector('.streamers-page'))loadScouts(root);},6000);}
async function save(page,config){snapshot={...await api('/api/scouts',{method:'PUT',body:config}),companion:snapshot.companion};paint(page,false,true);}
export async function handleScoutsClick(event){
 const button=event.target.closest('[data-scout-action], [data-scout-toggle], [data-scout-category], [data-scout-force-category], [data-scout-remove], [data-favorite-category]');if(!button)return;
 const page=button.closest('.streamers-page');if(!page||!snapshot||busy)return;button.disabled=true;busy++;epoch++;
 try{
  if(button.dataset.scoutAction==='reset-davey'){
   const holder=page.querySelector('[data-davey-preferences]'),old=JSON.parse(holder.dataset.progression);
   if(!globalThis.confirm('Reset personal Davey memory and validation? Personal reason counts and notes on this computer will be cleared when the companion next connects. Automatic posting will stop. Clip decision history stays. Unsaved controls will be discarded.'))return;
   await api('/api/davey/reset',{method:'POST',body:{revision:old.revision,confirmed:true}});await refreshWorkspace();delete boards.triggerDraft;boards.notice='Davey reset. Personal sharing and automatic posting are off. The companion will clear local memory on its next connection.';paint(page,true);return;
  }
  let cfg={...snapshot.configuration,slots:Number(page.querySelector('[name="slots"]')?.value??snapshot.configuration.slots)};
  if(button.dataset.favoriteCategory){
   const platform=button.dataset.platform,item=boards[platform].favoriteMatches?.category?.find(v=>v.id===button.dataset.favoriteCategory);
   if(!item)throw Error('Find the category again before adding it.');
   cfg=updateSelection(cfg,'forcedCategories',item,snapshot.limits,{addOnly:true});
   boards.notice='Favorite category saved. Scouts will prioritize it when live.';
  }
  if(button.dataset.scoutAction==='manual'){await requestManualTrigger(button.dataset.platform,button.dataset.login);boards.notice='Clip requested. The scout needs a full before buffer and processing capacity; it will keep watching.';paint(page);return;}
  if(button.dataset.scoutAction==='quick-settings'){boards.quickSettings=!boards.quickSettings;paint(page);return;}
  if(button.dataset.scoutAction==='allocation'){const platform=button.dataset.platform,allocation=cfg.platformSlots??{twitch:Math.ceil(cfg.slots/2),kick:Math.floor(cfg.slots/2)};const next={...allocation,[platform]:Math.max(0,allocation[platform]+Number(button.dataset.delta))};cfg={...cfg,platformSlots:next,slots:next.twitch+next.kick};if(cfg.slots>snapshot.limits.scouts)throw Error('Your scout allowance is fully allocated.');if(!cfg.slots)cfg.running=false;boards.notice='Scout allocation saved. The companion will apply it shortly.';await save(page,cfg);return;}
  if(button.dataset.scoutAction==='tab'){boards[button.dataset.platform].tab=button.dataset.tab;paint(page);return;}
  if(button.dataset.scoutAction==='refresh'){lastDirectory=0;await loadScouts(page.parentElement);return;}
  if(button.dataset.scoutToggle){const item=directoryItem(rows,button.dataset.platform,button.dataset.sourceLogin);if(!item)throw Error('Refresh the source list.');cfg=updateSelection(cfg,button.dataset.scoutToggle,item,snapshot.limits);}
  for(const [attribute,kind] of [['scoutCategory','categories'],['scoutForceCategory','forcedCategories']])if(button.dataset[attribute]!==undefined){const item=directoryItem(categories,button.dataset.platform,button.dataset[attribute],'id');if(!item)throw Error('Refresh the category list.');cfg=updateSelection(cfg,kind,item,snapshot.limits);}
  if(button.dataset.scoutRemove){const kind=button.dataset.scoutRemove;cfg[kind]=cfg[kind].filter(v=>!(v.platform===button.dataset.platform&&(v.login??v.id)===button.dataset.id));}
  await save(page,cfg);
 }catch(error){failure(error,page);}finally{busy--;button.disabled=false;}
}
export async function handleScoutsSubmit(event){
 const form=event.target.closest('[data-stream-settings], [data-scout-search], [data-favorite-entry]');if(!form)return;event.preventDefault();const page=form.closest('.streamers-page');if(!snapshot||busy)return;const requestEpoch=++epoch;
 busy++;
 try{
  const data=new FormData(form);
  if(form.dataset.favoriteEntry){
   const platform=form.dataset.platform,kind=form.dataset.favoriteEntry,query=String(data.get('query')??'').trim();
   if(!query||query.length>100)throw Error('Enter a valid channel username or category name.');
   if(kind==='streamer'&&!/^[a-zA-Z0-9_-]{1,35}$/.test(query))throw Error('Enter the channel username only.');
   const result=await directory(platform,query,kind==='category'?'categories':'streams');
   if(requestEpoch!==epoch)return;
   if(kind==='category'){
    boards[platform].favoriteMatches={...boards[platform].favoriteMatches,category:result.result};
    boards.notice=result.result.length?'Choose a matching category to add.':'No matching categories found.';paint(page,false,true);return;
   }
   const item=result.result.find(v=>v.platform===platform&&v.login===query.toLowerCase());
   if(!item)throw Error('That channel could not be found. Check the username.');
   const config=updateSelection(snapshot.configuration,'forced',item,snapshot.limits,{addOnly:true});
   const index=rows.findIndex(v=>v.platform===platform&&v.login===item.login);if(index<0)rows.push(item);else rows[index]=item;
   boards.notice='Favorite streamer saved. Scouts will prioritize it when live.';await save(page,config);return;
  }
  if(form.matches('[data-stream-settings]')){
   const slots=Number(data.get('slots')),allocation=snapshot.configuration.platformSlots;
   const configuration={...snapshot.configuration,slots,...(allocation&&slots!==snapshot.configuration.slots?{platformSlots:{twitch:Math.ceil(slots/2),kick:Math.floor(slots/2)}}:{})};
   const controls={captureCapacity:Math.max(1,slots),sensitivity:String(data.get('sensitivity')),captureGate:snapshot.controls?.captureGate??'balanced',captureSeconds:snapshot.controls?.captureSeconds??120,minClipSeconds:Number(data.get('minClipSeconds')),maxClipSeconds:Number(data.get('maxClipSeconds'))};
   const triggers=readTriggerSettings(form.querySelector('[data-scout-triggers]'));
   const preferences=Object.fromEntries(['focus','avoid','usagePreset','approval'].map(k=>[k,String(data.get(k))]));
   const progression=readDaveyProgression(form);if(progression)preferences.progression=progression;
   await saveStreamSettings({configuration,controls,triggers,preferences});boards.triggers=triggers;delete boards.triggerDraft;
   await refreshWorkspace();snapshot={...await api('/api/scouts'),companion:snapshot.companion};boards.notice='Scout, clip trigger and Davey settings saved.';paint(page,true);return;
  }
  const result=await directory(form.dataset.platform,String(data.get('query')??''),form.dataset.searchKind);if(requestEpoch!==epoch)return;applyDirectory(result);paint(page,false,true);
 }catch(error){failure(error,page);}finally{busy--;}
}
