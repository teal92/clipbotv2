import test from 'node:test';
import assert from 'node:assert/strict';
import {renderProcessing} from '../frontend/js/views/processing.js';
import {renderPublishing} from '../frontend/js/views/publishing.js';
import {renderLogs} from '../frontend/js/views/logs.js';
import * as processing from '../frontend/js/controllers/processing-controller.js';
import {loadSession,resetSession} from '../frontend/js/service-state.js';

const id=n=>String(n).padStart(32,'0');
test('Processing exposes companion version and bounded understandable hardware metrics',()=>{
 const html=renderProcessing({workerConnected:true,scouts:{companion:{companionVersion:'0.2.9-beta'}},pipelineJobs:[{stage:'capturing',metrics:{cpuPercent:33,memoryPercent:46,freeDiskBytes:12*1024**3}}]});
 assert.match(html,/Companion connected \(version 0.2.9-beta\)/);
 for(const text of ['CPU usage','Memory usage','Free disk space','33%','46%','12 GiB'])assert.ok(html.includes(text),text);
 assert.doesNotMatch(html,/Check Logs|Check status|Connect Accounts/);
 assert.match(html,/Download logs bundle/);
 assert.match(html,/only after the session ends/);
 const unknown=renderProcessing({pipelineJobs:[{stage:'capturing',metrics:{cpuPercent:NaN,memoryPercent:999,freeDiskBytes:-1}}]});
 assert.doesNotMatch(unknown,/NaN|999%|-1 GiB|<meter[^>]*value="999"/);
});
test('Processing bundle is disabled for running, invalid and missing sessions and exports only a real completed session',()=>{
 assert.equal(typeof processing.renderProcessingSessionDownload,'function');
 const stopped={id:id(1),state:'stopped',startedAt:'2026-10-12T10:00:00Z',stoppedAt:'2026-10-12T11:00:00Z'};
 assert.match(processing.renderProcessingSessionDownload([stopped]),new RegExp(`/api/logs/sessions/${id(1)}`));
 for(const sessions of [[],[{...stopped,state:'running',stoppedAt:null}],[{...stopped,state:'stopped',stoppedAt:null}],[{...stopped,id:'../secret'}],[stopped,{...stopped,id:id(2),state:'running',stoppedAt:null}]]){
  const html=processing.renderProcessingSessionDownload(sessions);
  assert.match(html,/disabled/);assert.doesNotMatch(html,/href=/);
 }
});
test('Publishing keeps completed and failed social results inline without logs or delivery cards',()=>{
 const clip={id:id(1),title:'Clip',caption:'Caption',artifact:{duration:20}};
 const publications=['tiktok','instagram','facebook'].map((platform,n)=>({id:id(n+2),clipId:clip.id,platform,status:'published',updated:1}));
 const html=renderPublishing(undefined,{ready:[clip],publications},{platforms:[]});
 for(const name of ['TikTok','Instagram','Facebook'])assert.match(html,new RegExp(name+': Published'));
 assert.doesNotMatch(html,/publishing-logs"|publish-history|publish-delivery-card|Publishing logs|Delivery history|Delivery in progress/);
 assert.match(html,/Download logs bundle/);assert.match(html,new RegExp(`/api/pipeline/publishing-logs/${id(1)}`));
 const failure=renderPublishing(undefined,{ready:[clip],publications:[{...publications[0],status:'failed'}]},{platforms:[]});
 assert.match(failure,/TikTok: Failed/);
 assert.match(renderPublishing(undefined,{ready:[],publications:[]},{platforms:[]}),/disabled[^>]*>Download logs bundle/);
});
test('Logs removes the obsolete account connection shortcut',()=>assert.doesNotMatch(renderLogs([]),/Open Connect Accounts|data-open-view="connections"/));
test('Processing hydration discards responses after an account change',async()=>{
 assert.equal(typeof processing.loadProcessingDiagnostics,'function');
 const previous=globalThis.fetch;let release;
 globalThis.fetch=async path=>path==='/api/account'?{ok:true,json:async()=>({user:{id:'owner'},csrfToken:'csrf'})}:path==='/api/logs/sessions'?new Promise(resolve=>{release=()=>resolve({ok:true,json:async()=>({sessions:[{id:id(1),state:'stopped',startedAt:'2026-10-12T10:00:00Z',stoppedAt:'2026-10-12T11:00:00Z'}]})});}):{ok:true,json:async()=>({})};
 const slot={innerHTML:'Current account'},page={isConnected:true,matches:()=>true,querySelector:()=>slot};
 try{await loadSession();const pending=processing.loadProcessingDiagnostics(page);while(!release)await new Promise(resolve=>setImmediate(resolve));resetSession();release();await pending;assert.equal(slot.innerHTML,'Current account');}
 finally{resetSession();globalThis.fetch=previous;}
});
