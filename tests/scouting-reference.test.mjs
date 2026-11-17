import test from 'node:test';
import assert from 'node:assert/strict';
import {renderStreamers,renderMonitoring} from '../frontend/js/views/streamers.js';
import * as pipeline from '../frontend/js/controllers/pipeline-controller.js';
const config={running:true,slots:2,forced:[{platform:'twitch',login:'forced'}],favorites:[{platform:'kick',login:'favorite'}],categories:[],forcedCategories:[{platform:'kick',id:'g',name:'Game'}]};
const snapshot={configuration:config,limits:{scouts:3,favorites:2,categories:2},companion:{companionVersion:'0.2.4-beta',monitoredSources:[{platform:'twitch',login:'forced',started:Date.now()/1000-40,state:'monitoring'},{platform:'kick',login:'favorite',started:Date.now()/1000-20,state:'reconnecting'}]}};
test('Scouting shows category coverage then reported monitor rows, while Streamers retains selection controls',()=>{
 const rows=[{platform:'twitch',login:'forced',categoryId:'g',categoryName:'Game',viewers:123,live:true},{platform:'kick',login:'favorite',categoryId:'g',categoryName:'Game',viewers:45,live:true}];
 const categories=[{platform:'twitch',id:'g',name:'Game',viewers:123},{platform:'kick',id:'g',name:'Game',viewers:45}];
 const html=renderStreamers(snapshot,rows,categories,null,{},'scouting');
 assert.match(html,/data-category-coverage="twitch"/);assert.match(html,/data-category-coverage="kick"/);assert.match(html,/data-monitor-table="twitch"/);assert.ok(html.indexOf('data-category-coverage')<html.indexOf('data-monitor-table'));
 assert.match(html,/forced/);assert.match(html,/123 viewers/);
 const selection=renderStreamers(snapshot,rows,categories,null,{},'streamers');
 assert.match(selection,/data-scout-controls/);assert.match(selection,/data-scout-toggle="forced"/);assert.match(selection,/scout-priority/);assert.match(selection,/aria-pressed="true"/);
});
test('current companion monitors render without pipeline jobs and absent telemetry stays unknown',()=>{
 const html=renderMonitoring(snapshot,[{platform:'twitch',login:'forced',categoryName:'Game',viewers:123},{platform:'kick',login:'favorite',categoryId:'g',categoryName:'Game'}],{pipelineJobs:[]});
 const twitch=html.split('data-monitor-table="twitch"')[1].split('data-monitor-table="kick"')[0];
 assert.match(twitch,/<td>forced<\/td>/);assert.match(twitch,/Favorite streamer/);assert.match(twitch,/<th>Chunks<\/th>/);assert.match(twitch,/<th>Spikes<\/th>/);assert.match(twitch,/<th>Score<\/th>/);assert.match(twitch,/<td>—<\/td>/);assert.match(html,/Favorite category/);assert.match(html,/Reconnecting/);
});
test('polling carries the recent failures disclosure state to refreshed markup',()=>{
 assert.equal(typeof pipeline.preservePipelineDisclosures,'function');
 const old={dataset:{pipelineDisclosure:'history'},open:true};const fresh={dataset:{pipelineDisclosure:'history'},open:false};
 pipeline.preservePipelineDisclosures({querySelectorAll:()=>[old]},{querySelectorAll:()=>[fresh]});assert.equal(fresh.open,true);
 old.open=false;pipeline.preservePipelineDisclosures({querySelectorAll:()=>[old]},{querySelectorAll:()=>[fresh]});assert.equal(fresh.open,false);
});
import {loadPipeline} from '../frontend/js/controllers/pipeline-controller.js';
import {resetSession} from '../frontend/js/service-state.js';
test('automatic pipeline refresh updates failure counts without closing an open history',async()=>{
 const previousFetch=globalThis.fetch,previousDocument=globalThis.document;
 const old={dataset:{pipelineDisclosure:'history'},open:true},fresh={dataset:{pipelineDisclosure:'history'},open:false};let rendered='';
 const parent={querySelectorAll:selector=>selector==='[data-pipeline-disclosure]'?[fresh]:[]};
 const page={isConnected:true,parentElement:parent,matches:selector=>selector==='.processing-page',querySelector:()=>null,querySelectorAll:selector=>selector==='[data-pipeline-disclosure]'?[old]:[],set outerHTML(value){rendered=value;}};
 globalThis.document={activeElement:null};globalThis.fetch=async(path)=>({ok:true,json:async()=>path==='/api/workspace'?{pipelineJobs:[{id:'failed',source:{platform:'kick',login:'channel'},stage:'failed',errorCode:'capture_unavailable'}]}:path==='/api/account'?{user:{id:'history-test'}}:{}});
 try{await loadPipeline({querySelector:()=>page});assert.match(rendered,/Recent failures and stopped jobs \(1\)/);assert.equal(fresh.open,true);}
 finally{resetSession();globalThis.fetch=previousFetch;globalThis.document=previousDocument;}
});
test('reconnecting scouts keep their actual state and never receive the active gold class',()=>{
 const html=renderMonitoring(snapshot,[],{pipelineJobs:[]});
 const card=html.split('data-preview-key="kick:favorite"')[1].split('</article>')[0];
 assert.doesNotMatch(card,/class="workspace-card scout-active/);assert.match(card,/Reconnecting/);
});
import {reconcilePreviewCard} from '../frontend/js/controllers/scouts-controller.js';
test('mounted live previews re-enable manual capture when the scout reconnects',()=>{
 const button={disabled:true},freshButton={disabled:false};const replaceable={replaceWith(){}};
 const old={className:'workspace-card',querySelector:selector=>selector==='[data-scout-action="manual"]'?button:selector==='details'?{open:true}:replaceable};
 const fresh={className:'workspace-card scout-active',querySelector:selector=>selector==='[data-scout-action="manual"]'?freshButton:replaceable};
 reconcilePreviewCard(old,fresh);assert.equal(button.disabled,false);assert.match(old.className,/scout-live-expanded/);
});
import * as scoutController from '../frontend/js/controllers/scouts-controller.js';
test('category coverage deduplicates in-flight reads, caches thirty seconds and retains last known data on failure',async()=>{
 assert.equal(typeof scoutController.createCategoryCoverageLoader,'function');
 let now=1000,calls=0,release;const gate=new Promise(resolve=>{release=resolve;});
 const read=async(path)=>{calls++;assert.match(path,/category-coverage/);assert.equal(new URL(path,'https://clip.test').searchParams.get('categories'),'1,2,3,4,5,6,7,8,9,10');await gate;return {sources:[{platform:'twitch',login:'observed',categoryId:'1',viewers:10,live:true}],errors:{}};};
 const loader=scoutController.createCategoryCoverageLoader(read,()=>now),categories=Array.from({length:12},(_,i)=>({id:String(i+1)}));
 const first=loader('owner','twitch',categories),second=loader('owner','twitch',categories);release();assert.deepEqual(await first,await second);assert.equal(calls,1);
 await loader('owner','twitch',categories);assert.equal(calls,1);now=31001;await loader('owner','twitch',categories);assert.equal(calls,2);
 let fail=false;const fallback=scoutController.createCategoryCoverageLoader(async()=>{if(fail)throw Error('offline');return {sources:[{login:'real'}],errors:{}};},()=>now);
 await fallback('owner','kick',categories);fail=true;now+=30001;const stale=await fallback('owner','kick',categories);assert.equal(stale.sources[0].login,'real');assert.equal(stale.stale,true);assert.match(stale.error,/offline/);
});
test('a forced category labels only its top eligible streamer, not a lower favorite in the same game',()=>{
 const data=[{platform:'kick',login:'top',categoryId:'g',categoryName:'Game',live:true,viewers:900},{platform:'kick',login:'favorite',categoryId:'g',categoryName:'Game',live:true,viewers:50}];
 const html=renderMonitoring(snapshot,data,{pipelineJobs:[]});
 const row=html.split('<td>favorite</td>')[1].split('</tr>')[0];assert.match(row,/<td>Auto<\/td>/);assert.doesNotMatch(row,/Forced category/);
});
test('currently monitoring tables appear between category coverage and live scout windows',()=>{
 const html=renderScoutingForOrder();assert.ok(html.indexOf('data-category-coverage')<html.indexOf('data-monitor-table'));assert.ok(html.indexOf('data-monitor-table')<html.indexOf('data-preview-key'));
});
function renderScoutingForOrder(){return renderStreamers(snapshot,[],[],null,{},'scouting');}
