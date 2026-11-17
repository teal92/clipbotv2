import {selectionOutcome} from '../selection-outcomes.js';
import {getCompanionStatus,companionStartAction} from '../controllers/companion-controller.js';

import {escapeHtml as e} from '../ui-utils.js';

import {getActivity,redact,ACTIVITY_LEVELS} from '../activity.js';

const AREAS={ui:'App',davey:'Davey AI',settings:'Settings',processing:'Video processing',publishing:'Publishing',service:'Server connection',scouting:'Scouting',capture:'Capture',transcription:'Transcription',rendering:'Rendering',companion:'Companion'};

function explain(entry){
 const code=entry.message.match(/\((analysis_[a-z_]+|render_[a-z_]+)\)/)?.[1];
 const precise={analysis_invalid_json:['Davey returned unreadable clip data','The provider responded, but its clip data could not be read. No paid retry was started.'],analysis_invalid_range:['Davey selected an invalid time range','The selected range was outside the recording or your clip length limits.'],analysis_invalid_transcript:['The transcript did not fit the recording','Whisper timestamps or transcript limits failed validation before paid analysis.'],analysis_provider_auth:['Davey service access was refused','The service owner must check the configured provider credentials.'],analysis_provider_rate_limit:['Davey provider is busy','The provider refused this request because of a rate limit. No paid retry was started.'],analysis_provider_timeout:['Davey response timed out','Check Usage for reconciliation. ClipBot will not repeat the paid request automatically.'],analysis_budget:['Davey spending limit reached','Check Usage. The spending safeguard remains active.'],render_tool_missing:['The local video tool is missing','Use Check companion to update the companion, then keep it running.'],render_encode_failed:['The video could not be encoded','FFmpeg did not finish the mobile clip. Check the companion and the rendering events for this job.'],render_verify_failed:['The finished video failed verification','ClipBot blocked the unverified video from approval and publishing.'],render_timeout:['The local video render timed out','Reduce local load and check the companion. The original recording stays on this computer.']};
 if(precise[code])return {title:precise[code][0],help:precise[code][1]};

 if(/Davey.*paused|enable.*Davey/i.test(entry.message))return {title:'Enable Davey before scouting',help:'Check your Streamers preferences and plan allowance, then use Start ClipBot at the top.'};

 if(/companion.*update|update.*companion|dependencies.*incompatible/i.test(entry.message)&&companionStartAction(getCompanionStatus())==='start')return {title:'Earlier companion update warning',help:'The connected companion is now up to date. This warning was recorded before the update.'};

 if(/companion.*update|update.*companion|dependencies.*incompatible/i.test(entry.message))return {title:'Your companion needs an update',help:'Use Check companion to download the latest companion from the website.'};

 if(/beta.*acknowledge|Acknowledge beta/i.test(entry.message))return {title:'Review feedback privacy',help:'Open Streamers and acknowledge the feedback privacy notice before starting.'};

 if(/Earlier companion versions/i.test(entry.message))return {title:'Earlier capture failure',help:'This older job has no detailed failure reason. Check the companion version and current jobs in Processing; restarting this old entry will not recover its recording.'};

 if(/could not be recorded|capture-quality/i.test(entry.message))return {title:'The recording could not be captured',help:'The stream may have ended or the recording did not meet Capture quality. Check the current stream and the quality setting in Scouting.'};

 if(/no usable speech/i.test(entry.message))return {title:'No speech found in the recording',help:'This recording had no usable transcript for Davey. Scouting can continue with the next window.'};

 if(/spending safeguard|review allowance|spending ceiling/i.test(entry.message))return {title:'Davey reached a spending or review limit',help:'Check Usage and your Davey settings. ClipBot keeps the spending limit in place and does not retry paid analysis automatically.'};

 if(/permitted number of reviews/i.test(entry.message))return {title:'Davey review capacity is full',help:'Wait for the current reviews to finish. Check your scout count against the processing capacity.'};

 if(/Davey analysis did not finish/i.test(entry.message))return {title:'Davey could not finish this review',help:'Check Usage and the live test status. Automatic paid retries are disabled.'};

 if(/storage|quota/i.test(entry.message)&&!['processing','publishing'].includes(entry.source))return {title:'ClipBot could not save your changes',help:'Check browser storage permissions and try saving again.'};

 const descriptions={service:{title:'ClipBot could not reach the server',help:'Check your internet connection, then try Check Connection. If it continues, contact support.'},processing:{title:'A video could not be processed',help:'Check that your local worker is running, then retry the clip.'},publishing:{title:'A clip could not be published',help:'Check the connected platform account before retrying. Confirm whether the post already exists.'},davey:{title:'Davey could not finish an analysis',help:'Try again later. If it continues, contact support.'},settings:{title:'Your preferences could not be saved',help:'Choose a listed preset and try again.'},ui:{title:'ClipBot ran into a problem',help:'Refresh the page and try again. If it continues, share the details below with support.'}};

 return descriptions[entry.source]??descriptions.ui;

}

export function renderLogEntries(entries){

 return entries.length?entries.slice().reverse().map(entry=>{

 const outcome=selectionOutcome(entry.message.match(/\((analysis_[a-z_]+|not_selected)\)/)?.[1]);
 const displayLevel=outcome?'info':entry.level;
 const info=outcome??(entry.level==='error'?explain(entry):{title:entry.level==='warning'?'Pipeline warning':entry.level==='debug'?'Debug event':'Pipeline activity',help:null});

 return `<article class="readable-error diagnostic-event diagnostic-${e(displayLevel)}"><div class="error-heading"><strong>${e(info.title)}</strong><time>${e(new Date(entry.createdAt).toLocaleString())}</time></div>${info.help?`<p>${e(info.help)}</p>`:''}<span>${e(AREAS[entry.source]??'App')} &middot; ${e(displayLevel)}</span><p class="diagnostic-message">${e(redact(entry.message))}</p><details data-log-id="${e(entry.id??'')}"><summary>Details for support</summary><pre>${e(redact(entry.message))}${entry.details?'\n'+e(JSON.stringify(entry.details,null,2)):''}</pre></details></article>`;

 }).join(''):'<div class="error-empty"><strong>No activity recorded</strong><p>Pipeline activity appears here when streams, processing or publishing report new events.</p></div>';

}

// Order by the actual start instant; API order and running state never hide a newer run.
export function renderSessionBundles(sessions){
 const timeOf=session=>typeof session.startedAt==='string'?Date.parse(session.startedAt):NaN;
 const ranked=(Array.isArray(sessions)?sessions:[]).filter(session=>session&&typeof session.id==='string'&&/^[a-f0-9]{32}$/.test(session.id)).slice().sort((a,b)=>{
  const left=timeOf(a),right=timeOf(b);
  return (Number.isFinite(right)?right:-Infinity)-(Number.isFinite(left)?left:-Infinity)||Number(b.state==='running')-Number(a.state==='running')||a.id.localeCompare(b.id);
 });
 const seen=new Set(),ordered=ranked.filter(session=>{if(seen.has(session.id))return false;seen.add(session.id);return true;});
 if(!ordered.length)return '<p class="session-bundle-empty">No monitoring sessions recorded yet. Press Start ClipBot to begin one.</p>';
 return `<ul class="session-bundle-list">${ordered.map((session,index)=>{
  const latest=index===0,state=session.state==='running'?'Running':session.state==='stopped'?'Stopped':'Unknown state';
  const instant=timeOf(session),date=Number.isFinite(instant)?new Date(instant):null;
  const label=date?date.toLocaleString():'Start time unavailable';
  return `<li data-session-id="${session.id}" class="session-bundle-row${latest?' session-bundle-latest':''}"><div class="session-bundle-info"><div class="session-bundle-heading">${latest?'<span class="session-bundle-badge">Latest</span>':'<strong>Session</strong>'}<span class="session-bundle-state">${state}</span></div>${date?`<time datetime="${date.toISOString()}">${e(label)}</time>`:`<span>${label}</span>`}</div>${session.state==='stopped'?`<a class="btn session-bundle-download" href="/api/logs/sessions/${session.id}" download aria-label="${e(`Download ${latest?'latest ':''}${state.toLowerCase()} session started ${label}`)}">Download</a>`:'<button class="btn session-bundle-download" disabled title="Available after the session ends">Download after Stop</button>'}</li>`;
 }).join('')}</ul>`;
}

export function renderLogs(entries=getActivity()){

 return `<div class="logs-page workspace-page"><section class="section-block"><div class="section-heading"><div><span class="eyebrow">PIPELINE DIAGNOSTICS</span><h2>Pipeline &amp; Error Log</h2><p>Follow scouting, capture, transcription, Davey analysis, editing and publishing in one place.</p></div></div></section>

 <section class="workspace-card"><div class="workspace-toolbar error-toolbar"><label for="log-search">Search</label><input id="log-search" type="search" data-log-search maxlength="200" placeholder="Search pipeline activity..."><label for="log-source">Area</label><select id="log-source" data-log-source><option value="all">All areas</option>${Object.entries(AREAS).map(([id,label])=>`<option value="${id}">${label}</option>`).join('')}</select><label for="log-level">Level</label><select id="log-level" data-log-level><option value="all">All levels</option>${ACTIVITY_LEVELS.map(level=>`<option value="${level}">${level}</option>`).join('')}</select><button type="button" class="btn" data-workspace-action="refresh-logs">Refresh</button><button type="button" class="btn" data-workspace-action="clear-logs">Clear Browser Logs</button></div><p data-workspace-status role="status" aria-live="polite">Checking server activity&hellip;</p><div class="bounded-log-list" data-log-entries role="log" aria-live="polite">${renderLogEntries(entries)}</div><p>The latest 200 events are kept on this browser. Refresh fetches server activity; updates continue every five seconds while this page is open.</p></section>

 <section class="workspace-card"><h3>Session debugging bundles</h3><p>Each monitoring run is bundled from Start to Stop. Download the current or a recent session to share for debugging.</p><div class="session-bundles" data-debug-sessions tabindex="0" role="region" aria-label="Session debugging bundles">Loading sessions…</div><h3>Live Pipeline Feed</h3><p>Activity uses safe stage messages and error codes. Credentials, media access links and transcripts are removed from diagnostics. Companion console output stays on your computer; stage updates appear here when the companion reports them.</p></section></div>`;

}
