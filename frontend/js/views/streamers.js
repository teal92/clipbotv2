import {renderStreamInteraction} from './stream-interaction.js';
import {renderDaveyPreferences} from './davey.js';
import {renderBetaFeedback} from './beta-feedback.js';
import {renderTriggerControls} from './trigger-controls.js';
import {clipWorkflowCounts} from './workflow.js';
import {getWorkspace,getAccount} from '../service-state.js';

import {escapeHtml as e} from '../ui-utils.js';

const EMPTY={configuration:{running:false,slots:0,forced:[],favorites:[],categories:[],forcedCategories:[]},limits:{scouts:0,favorites:0,categories:0}};

export function renderStreamers(snapshot=getWorkspace().scouts??EMPTY,rows=[],categories=[],testStatus=null,boards={},view='streamers'){

 const cfg=snapshot.configuration,limits=snapshot.limits,slots=cfg.slots,controls=snapshot.controls??{sensitivity:'balanced',captureGate:'balanced',captureSeconds:120,minClipSeconds:15,maxClipSeconds:60,captureCapacity:2};

 const hints={captureCapacity:'Maximum streams recorded at once on this computer. Actual capacity is the lower of this setting and your scout slots.',sensitivity:'Minimum Davey score to keep a candidate: loose 60, balanced 75, strict 90.',captureGate:'How much of the capture window must be recorded. Review accepts playable short captures; balanced requires half; strict requires 90%.',captureSeconds:'Length of each recorded window sent for analysis. Longer windows use more local disk and processing.',minClipSeconds:'Shortest clip Davey may select from a recorded window.',maxClipSeconds:'Longest clip Davey may select. Must fit inside the capture window.'};

 const select=(name,label,values)=>`<label title="${e(hints[name])}">${label} <span class="scout-help" tabindex="0" aria-label="${e(hints[name])}">&#9432;<span role="tooltip">${e(hints[name])}</span></span><select name="${name}">${values.map(v=>`<option value="${v[0]}" ${String(controls[name])===String(v[0])?'selected':''}>${v[1]}</option>`).join('')}</select></label>`;

 const selected=(kind,item)=>cfg[kind]?.some(v=>v.platform===item.platform&&(v.login??v.id)===(item.login??item.id));

 const targetStatus=(platform,kind,item)=>{
  const monitored=snapshot.companion?.monitoredSources??[];
  if(monitored.some(v=>v.platform===platform&&v.state==='monitoring'&&(kind==='forced'?v.login===item.login:rows.some(r=>r.platform===platform&&r.login===v.login&&r.categoryId===item.id))))return 'Monitoring';
  const live=rows.filter(r=>r.platform===platform&&(kind==='forced'?r.login===item.login:r.categoryId===item.id));
  return live.some(r=>r.live===true)?'Live':live.length&&live.every(r=>r.live===false)?'Waiting · offline':'Waiting · checking status';
 };
 const chips=(platform,kind)=>cfg[kind]?.filter(v=>v.platform===platform).map(v=>`<span class="scout-chip ${['forced','forcedCategories'].includes(kind)?'scout-priority':''}">${e(v.login??v.name)} ${['forced','forcedCategories'].includes(kind)?`<small>${e(targetStatus(platform,kind,v))}</small>`:''} <button type="button" data-scout-remove="${kind}" data-platform="${platform}" data-id="${e(v.login??v.id)}" aria-label="Remove ${e(v.login??v.name)}">×</button></span>`).join('')||'<span class="muted">None</span>';

 const platformPanel=platform=>{

  const board=boards[platform]??{},tab=board.tab??'streams',sources=rows.map((s,i)=>({...s,index:i})).filter(s=>s.platform===platform),games=categories.map((s,i)=>({...s,index:i})).filter(s=>s.platform===platform),active=(snapshot.companion?.monitoredSources??getWorkspace().sources??[]).filter(v=>v.platform===platform&&(!v.state||v.state==='monitoring'));

  const streamRows=sources.map((s,rank)=>`<article class="scout-directory-row ${selected('forced',s)?'scout-priority':''} ${selected('favorites',s)?'scout-favorite':''} ${active.some(v=>v.login===s.login)?'scout-active':''}"><div><strong><span class="scout-rank">${rank+1}.</span> ${e(s.login)}</strong><small>${s.live?'Live':'Offline'} · ${e(s.categoryName??'')} · ${e((s.viewers??0).toLocaleString())} viewers</small></div><div><button class="btn scout-selection ${selected('forced',s)?'scout-selected':''}" aria-pressed="${Boolean(selected('forced',s))}" data-scout-toggle="forced" data-source-login="${e(s.login)}" data-platform="${platform}">${selected('forced',s)?'Remove favorite':'Favorite streamer'}</button></div></article>`).join('');

  const categoryRows=games.map((s,rank)=>`<article class="scout-directory-row ${selected('forcedCategories',s)?'scout-priority':''} ${selected('categories',s)?'scout-favorite':''}"><div><strong><span class="scout-rank">${rank+1}.</span> ${e(s.name)}</strong>${Number.isFinite(s.viewers)?`<small>${e(s.viewers.toLocaleString())} viewers across listed live streams</small>`:''}${s.rankingBasis?'':''}</div><div><button class="btn scout-selection ${selected('forcedCategories',s)?'scout-selected':''}" aria-pressed="${Boolean(selected('forcedCategories',s))}" data-scout-force-category="${e(s.id)}" data-platform="${platform}">${selected('forcedCategories',s)?'Remove favorite':'Favorite category'}</button></div></article>`).join('');

  const search=kind=>`<form data-scout-search data-platform="${platform}" data-search-kind="${kind}"><input name="query" maxlength="100" placeholder="${kind==='streams'?'Find a streamer':'Find a category'}" aria-label="Search ${platform} ${kind}"><button class="btn" type="submit">Find</button></form>`;

  const entry=kind=>{
   const matches=board.favoriteMatches?.[kind]??[];
   return `<section class="scout-favorite-entry"><form data-favorite-entry="${kind}" data-platform="${platform}"><label>${kind==='streamer'?'Add favorite streamer':'Add favorite category'}<input name="query" required maxlength="100" aria-label="${platform} favorite ${kind}" placeholder="${kind==='streamer'?'Channel username':'Category name'}"></label><button class="btn" type="submit">${kind==='streamer'?'Add':'Find'}</button></form>${kind==='category'?`<div class="scout-favorite-results">${matches.map(item=>`<button class="btn" data-favorite-category="${e(item.id)}" data-platform="${platform}">Add ${e(item.name)}</button>`).join('')}</div>`:''}</section>`;
  };

  return `<section class="workspace-card scout-platform" data-platform-panel="${platform}"><div class="scout-platform-heading"><h3>${platform==='twitch'?'Twitch':'Kick'}</h3><span>${active.length} active scouts</span></div><div class="scout-platform-selections"><div><strong>Favorite streamers:</strong> ${chips(platform,'forced')}</div><div><strong>Favorite categories:</strong> ${chips(platform,'forcedCategories')}</div></div>${['favorites','categories'].some(kind=>cfg[kind]?.some(v=>v.platform===platform))?`<div class="scout-legacy-preferences"><small>Other saved preferences · normal priority</small><div>Streamers: ${chips(platform,'favorites')}</div><div>Category filters: ${chips(platform,'categories')}</div></div>`:''}<div class="scout-favorite-inputs">${entry('streamer')}${entry('category')}</div><small>Favorites take priority when live, within your scout slots. Other scouts keep watching while favorites are offline.</small>${snapshot.discoveryWarnings?.[platform]?`<p role="status">${e(snapshot.discoveryWarnings[platform])}</p><button class="btn" data-open-view="connections">Connect Accounts</button>`:''}${board.error?`<p role="status">${e(board.error)}</p>`:''}<div class="scout-directory-columns"><section><h4>Top streamers</h4>${search('streams')}<div class="scout-directory" aria-label="${platform} live directory">${streamRows||'<p>No live streamers returned.</p>'}</div></section><section><h4>Top categories</h4>${search('categories')}<div class="scout-directory">${categoryRows||'<p>No categories returned.</p>'}</div></section></div></section>`;



 };

 const reason={trigger_settings_unavailable:'Scouting paused: clip trigger settings could not be loaded. Refresh or reconnect the companion.',analysis_paused:'Davey reviews are paused. Check your preferences and plan allowance.',beta_required:'Read the feedback privacy notice below.',coverage_unavailable:'An active subscription is required.',tools_missing:'Use the companion check at the top of this page.'}[snapshot.companion?.errorCode];
 return `<div class="streamers-page workspace-page" data-scout-view="${view}"><section class="section-heading"><div><span class="eyebrow">LIVE SCOUTS</span><h2>${view==='scouting'?'Scouting':'Streamers'}</h2><p>${view==='scouting'?'Category coverage and live scouts.':'Your scouts, clip triggers and Davey preferences.'}</p></div><button class="btn" data-scout-action="refresh">Refresh status</button></section><p data-scout-status role="status" aria-live="polite">${e(boards.notice??reason??'')}</p>${view==='streamers'?`<section class="workspace-card scout-command-center"><form data-stream-settings><h3>Scouts and clips</h3><div data-scout-controls class="scout-control-grid"><label>Number of scouts<select name="slots">${Array.from({length:limits.scouts+1},(_,n)=>`<option value="${n}" ${n===slots?'selected':''}>${n}</option>`).join('')}</select></label>${select('sensitivity','Clip sensitivity',[['loose','Loose · score 60+'],['balanced','Balanced · score 75+'],['strict','Strict · score 90+']])}${select('minClipSeconds','Minimum clip',[[15,'15 sec'],[30,'30 sec'],[45,'45 sec'],[60,'60 sec']])}${select('maxClipSeconds','Maximum clip',[[15,'15 sec'],[30,'30 sec'],[45,'45 sec'],[60,'60 sec']])}</div><small>${e(limits.scouts)} scout slots allowed by your plan. Monitoring and rendering use your computer.</small>${renderTriggerControls(boards.triggerDraft??boards.triggers,{embedded:true,compact:true})}${renderDaveyPreferences()}<button type="submit" class="btn approve">Save clip settings</button><p data-scout-controls-status role="status" aria-live="polite">${e(boards.notice??'')}</p></form>${!getWorkspace().betaFeedback?.accepted?renderBetaFeedback(getWorkspace().betaFeedback):''}</section>`:''}<div class="workspace-grid scout-platform-grid">${view==='scouting'?renderCategoryCoverage(categories,boards.coverageRows??rows,snapshot,boards.coverageErrors??{})+renderMonitoring(snapshot,rows,getWorkspace(),'scouts',boards.coverageRows??rows):platformPanel('twitch')+platformPanel('kick')}</div></div>`;

}



export function renderScouting(snapshot,rows=[],categories=[],testStatus=null,boards={}){
 return renderStreamers(snapshot,rows,categories,testStatus,boards,'scouting');
}

export function renderCategoryCoverage(categories,rows,snapshot,errors={}){
 return `<section class="scout-category-coverage"><h3>Top category coverage</h3><div class="scout-coverage-platforms">${['twitch','kick'].map(platform=>{
  const top=categories.filter(c=>c.platform===platform).slice(0,10);
  return `<section class="workspace-card" data-category-coverage="${platform}"><h3>${platform==='twitch'?'Twitch':'Kick'}</h3><p>Top 10 categories · top 3 streamers in each category</p>${snapshot.discoveryWarnings?.[platform]?`<p role="status">${e(snapshot.discoveryWarnings[platform])}</p>`:''}${errors[platform]?`<p role="status">${e(errors[platform])}</p>`:''}<div class="scout-category-grid">${top.map((category,rank)=>{
   const live=rows.filter(r=>r.platform===platform&&r.live&&r.categoryId===category.id).sort((a,b)=>(b.viewers??0)-(a.viewers??0)).slice(0,3);
   return `<article class="scout-category-card"><h4>${rank+1}. ${e(category.name)}</h4>${Number.isFinite(category.viewers)?`<small>${e(category.viewers.toLocaleString())} viewers in listed streams</small>`:''}<ol>${live.map(r=>`<li><strong>${e(r.login)}</strong><span>${e(Number.isFinite(r.viewers)?r.viewers.toLocaleString():'—')} viewers</span></li>`).join('')}</ol>${errors[platform+':'+category.id]?`<small role="status">${e(errors[platform+':'+category.id])}</small>`:live.length<3?'<small>Fewer than three live streams returned</small>':''}</article>`;
  }).join('')||'<p>Category data unavailable. Refresh status or check Connect Accounts.</p>'}</div></section>`;
 }).join('')}</div></section>`;
}

export function renderMonitoring(snapshot,rows=[],workspace=getWorkspace(),watchTab='scouts',coverageRows=rows){

 const jobs=workspace.pipelineJobs??[],now=Date.now()/1000,counts=clipWorkflowCounts(jobs);

 const actual=snapshot.companion?.monitoredSources;
 const running=Array.isArray(actual)?actual.map(s=>({source:s,stage:s.state==='monitoring'?'capturing':s.state??'connecting',created:s.started,updated:now,monitor:s})):jobs.filter(j=>j.stage==='capturing'&&j.updated>now-90);

 const forced=s=>snapshot.configuration.forced?.some(v=>v.platform===s.platform&&v.login===s.login);

 const forcedCategory=(source,categoryId)=>snapshot.configuration.forcedCategories?.some(category=>{
  if(category.platform!==source.platform||category.id!==categoryId)return false;
  const eligible=coverageRows.filter(row=>row.platform===source.platform&&row.categoryId===categoryId&&row.live!==false&&!forced(row)).sort((a,b)=>(b.viewers??0)-(a.viewers??0)||a.login.localeCompare(b.login));
  return eligible[0]?.login===source.login;
 });

 const table=platform=>{
  const active=running.filter(j=>j.source.platform===platform);
  const recent=[...active];for(const job of [...jobs].sort((a,b)=>b.updated-a.updated).filter(j=>j.source.platform===platform&&j.updated>now-600)){if(!recent.some(v=>v.source.login===job.source.login))recent.push(job);}
  const recorded=active.filter(j=>j.monitor?j.monitor.state==='monitoring':j.stage==='capturing');
  return `<section class="workspace-card" data-monitor-table="${platform}"><h3>${platform==='twitch'?'Twitch':'Kick'} currently monitoring</h3><p>${recorded.length} monitoring now · ${snapshot.configuration.running?'Start requested':'Stopped'}</p>${snapshot.discoveryWarnings?.[platform]?`<p role="status">${e(snapshot.discoveryWarnings[platform])}</p><button class="btn" data-open-view="connections">Connect Accounts</button>`:''}<div class="scout-table-scroll"><table><thead><tr><th>Scout</th><th>Streamer</th><th>Category / game</th><th>Assignment</th><th>Time</th><th>Chunks</th><th>Clips</th><th>Spikes</th><th>Score</th><th>State</th></tr></thead><tbody>${recent.map((j,index)=>{
   const source=j.source,info=rows.find(r=>r.platform===platform&&r.login===source.login),recording=j.monitor?j.monitor.state==='monitoring':j.stage==='capturing'&&j.updated>now-90;
   const status=j.monitor?({monitoring:'Monitoring',connecting:'Connecting',reconnecting:'Reconnecting',stopping:'Stopping'}[j.monitor.state]??j.monitor.state):recording?'Monitoring':j.stage==='capturing'?'Waiting for heartbeat':({queued:'Waiting',transcribing:'Transcribing',analyzing:'Analyzing',rendering:'Editing',ready:'Clip ready',published:'Posted',failed:'Capture or processing failed',cancelled:'Stopped'}[j.stage]??j.stage);
   const categoryId=info?.categoryId??source.categoryId,assignment=forced(source)?'Favorite streamer':forcedCategory(source,categoryId)?'Favorite category':'Auto';
   const clips=jobs.filter(v=>v.source.platform===platform&&v.source.login===source.login&&['ready','published'].includes(v.stage)).length;
   const score=(workspace.candidates??[]).filter(v=>v.platform===platform&&v.creator===source.login&&Number.isFinite(v.score)).at(-1)?.score;
   return `<tr class="${recording?'scout-active':''} ${assignment!=='Auto'?'scout-priority scout-forced':''}"><td>${index+1}</td><td>${e(source.login)}</td><td>${e(info?.categoryName??source.categoryName??'—')}</td><td>${assignment}</td><td>${recording&&Number.isFinite(j.created)?Math.max(0,Math.floor(now-j.created))+'s':'—'}</td><td>${e(Number.isFinite(j.monitor?.chunks)?j.monitor.chunks:'—')}</td><td>${clips}</td><td>${e(Number.isFinite(j.monitor?.spikes)?j.monitor.spikes:'—')}</td><td>${e(Number.isFinite(score)?score+'%':'—')}</td><td>${e(status??'Unknown')}</td></tr>`;
  }).join('')||'<tr><td colspan="10">No recent scouting activity. Use Start ClipBot at the top of the page.</td></tr>'}</tbody></table></div><small>Clips and scores use recent job evidence. — means unavailable telemetry.</small></section>`;
 };

 const previews=running.map(j=>{

  const recording=j.monitor?j.monitor.state==='monitoring':j.stage==='capturing',monitorState=({connecting:'Connecting',reconnecting:'Reconnecting',stopping:'Stopping'}[j.monitor?.state]??j.monitor?.state??'Waiting');
  const s=j.source,info=rows.find(r=>r.platform===s.platform&&r.login===s.login),url=s.platform==='twitch'?`https://player.twitch.tv/?channel=${encodeURIComponent(s.login)}&parent=${encodeURIComponent(globalThis.location?.hostname??'localhost')}&muted=true&autoplay=true`:`https://player.kick.com/${encodeURIComponent(s.login)}?muted=true&autoplay=true`,image=snapshotImage(info?.thumbnailUrl,s.platform);

  return `<article data-preview-key="${e(s.platform+':'+s.login)}" data-scout-platform="${e(s.platform)}" class="workspace-card ${recording?'scout-active':''} ${forced(s)||forcedCategory(s,info?.categoryId??s.categoryId)?'scout-priority scout-forced':''}"><div class="scout-tile-heading"><strong>${e(s.login)}</strong><small>${e(s.platform)}</small></div><div class="scout-tile-stats"><span>${e(Number.isFinite(info?.viewers)?info.viewers.toLocaleString():'—')} viewers</span><span>${recording?Math.max(0,Math.floor(now-(j.created??now)))+'s watching':e(monitorState)}</span><span>${jobs.filter(v=>v.source.platform===s.platform&&v.source.login===s.login&&['ready','published'].includes(v.stage)).length} clips</span></div><div class="scout-snapshot">${image?`<img src="${e(image)}" alt="Latest ${e(s.login)} stream snapshot" loading="lazy" referrerpolicy="no-referrer">`:'<span>Snapshot unavailable</span>'}</div>${renderStreamInteraction(j.monitor??{},now)}<small class="scout-cue-status">${e(({warming_up:'Filling buffer',watching_for_cues:'Watching for cues',saving_clip:'Saving triggered clip',waiting_for_processing:'Monitoring · waiting for processing'}[j.monitor?.cueStatus])??(recording?'Monitoring':monitorState))} · Chat: ${e(j.monitor?.chatStatus??'unavailable')} · Speech: ${e(j.monitor?.speechStatus??'waiting')}</small><button class="btn" data-scout-action="manual" ${recording?'':'disabled'} data-platform="${e(s.platform)}" data-login="${e(s.login)}">Clip now</button><small class="scout-snapshot-note">Snapshot refreshes every 30 seconds; provider delays may apply.</small><details><summary>Go live</summary><iframe loading="lazy" data-scout-preview-src="${e(url)}" title="Live ${e(s.login)} preview" allowfullscreen></iframe></details></article>`;

 }).join('');

 const allocation=snapshot.configuration.platformSlots??{twitch:Math.ceil((snapshot.configuration.slots??0)/2),kick:Math.floor((snapshot.configuration.slots??0)/2)};
 const platformStatus=platform=>!allocation[platform]?'Disabled':!snapshot.configuration.running?'Stopped':!workspace.workerConnected?'Companion offline':snapshot.companion?.errorCode==='analysis_paused'?'Davey paused':running.some(j=>j.source.platform===platform&&(!j.monitor||j.monitor.state==='monitoring'))?'Monitoring streams':counts.processing>=(snapshot.configuration.slots??0)+2?'Waiting for processing':'Looking for streams';
 const summary=platform=>`<article class="scout-overview-stat" data-scout-platform="${platform}"><strong>${platform==='twitch'?'Twitch':'Kick'} scouts — ${e(platformStatus(platform))}</strong><div class="scout-allocation"><b>${running.filter(j=>j.source.platform===platform&&(!j.monitor||j.monitor.state==='monitoring')).length} / ${allocation[platform]}</b><button class="btn" data-scout-action="allocation" data-platform="${platform}" data-delta="-1" aria-label="Remove one ${platform} scout" ${allocation[platform]===0?'disabled':''}>&minus;</button><button class="btn" data-scout-action="allocation" data-platform="${platform}" data-delta="1" aria-label="Add one ${platform} scout" ${snapshot.configuration.slots>=(snapshot.limits?.scouts??40)?'disabled':''}>+</button></div><small>${allocation[platform]} allocated · ${(snapshot.limits?.scouts??40)} allowed across both services</small>${snapshot.discoveryWarnings?.[platform]&&allocation[platform]?`<p>${e(snapshot.discoveryWarnings[platform])}</p>`:''}</article>`;

 return `<div class="scout-watch-panel scout-activity-panel">${table('twitch')}${table('kick')}</div><div class="scout-watch-panel"><section class="scout-overview">${summary('twitch')}${summary('kick')}<article class="scout-overview-stat"><strong>Collected / Processing / Ready for review</strong><b>${counts.collected} / ${counts.processing} / ${counts.review}</b><small>From the most recent 100 jobs</small></article></section><h3 class="scout-live-heading">Live scout windows</h3><section class="scout-preview-grid">${previews||'<p>Scout windows appear when a stream connects. Use Start ClipBot at the top of the page.</p>'}</section><p class="scout-legend">Gold text: favorites. Other scouts use normal text.</p></div>`;

}



export function snapshotImage(value,platform,now=Date.now()){

 try{const url=new URL(value);const host={twitch:'static-cdn.jtvnw.net',kick:'images.kick.com'}[platform];if(!host||url.protocol!=='https:'||url.hostname!==host||url.username||url.password||url.port||url.hash)return null;url.searchParams.set('clipbot_preview',String(Math.floor(now/30000)));return url.href;}catch{return null;}

}
