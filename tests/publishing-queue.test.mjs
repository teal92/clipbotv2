import test from 'node:test';
import assert from 'node:assert/strict';
import {renderPublishing} from '../frontend/js/views/publishing.js';
import {handlePipelineClick} from '../frontend/js/controllers/pipeline-controller.js';
import {loadSession,resetSession} from '../frontend/js/service-state.js';
const clip={id:'a'.repeat(32),title:'Approved <title>',caption:'Approved caption',creator:'Creator',artifact:{sha256:'c'.repeat(64),duration:25},previewUrl:'http://127.0.0.1:8767/preview/'+'b'.repeat(64)};
const connections={platforms:['tiktok','instagram','facebook'].map(id=>({id,connected:true,status:'connected',accountName:id+' account'}))};
const workspace=()=>({ready:[clip],workerConnected:true,publications:[],pipelineJobs:[{id:clip.id,stage:'ready'}]});
test('approved clips render four horizontal posting actions and read-only metadata',()=>{
 const html=renderPublishing(undefined,workspace(),connections);
 for(const label of ['Post TikTok','Post Instagram','Post Facebook','Post all'])assert.ok(html.includes(label));
 assert.match(html,/data-publish-row/);assert.match(html,/Approved &lt;title&gt;/);
 assert.ok(!html.includes('name="caption"'));assert.ok(!html.includes('name="title"'));assert.ok(!html.includes('data-publishing-form'));assert.ok(!html.includes('Publishing workflow'));
 assert.match(html,/permission.*caption.*destination/i);
});
test('missing worker, metadata, connection or existing attempts never present an eligible post',()=>{
 for(const state of [{...workspace(),workerConnected:false},{...workspace(),ready:[{...clip,caption:''}]}])assert.match(renderPublishing(undefined,state,connections),/data-publish-platform="facebook"[^>]*disabled/);
 assert.match(renderPublishing(undefined,workspace(),{platforms:[]}),/data-publish-platform="facebook"[^>]*disabled/);
 for(const status of ['published','failed','unknown','prepared'])assert.match(renderPublishing(undefined,{...workspace(),publications:[{clipId:clip.id,platform:'facebook',status}]},connections),/data-publish-platform="facebook"[^>]*disabled/);
});
function rowFixture(platform='facebook'){
 const output={textContent:''},fields={hidden:true,dataset:{},querySelector:()=>null};
 const row={dataset:{publishRow:clip.id},isConnected:true,querySelector:selector=>selector==='[data-pipeline-status]'?output:selector==='[data-tiktok-fields]'?fields:null,querySelectorAll:()=>[button]};
 const page={querySelector:()=>output},button={dataset:{publishPlatform:platform},disabled:false,closest:selector=>selector==='[data-publish-row]'?row:page};
 return {button,row,output,event:{target:{closest:()=>button},preventDefault(){}}};
}
async function session(run,{state=workspace(),links=connections,onPost,settings}={}){
 const oldFetch=globalThis.fetch;let posts=[];
 globalThis.fetch=async(path,options={})=>{
  const body=options.body?JSON.parse(options.body):null;
  if(path==='/api/pipeline/publish'){posts.push(body);const result=onPost?await onPost(body):null;return {ok:true,json:async()=>result??({id:'d'.repeat(32),clipId:body.clipId,platform:body.platform,status:'prepared'})};}
  const data=path==='/api/account'?{user:{id:'publishing-test'},csrfToken:'test-token'}:path==='/api/workspace'?state:path==='/api/connections'?(typeof links==='function'?links():links):path==='/api/pipeline/tiktok-settings'?(typeof settings==='function'?settings():settings??{privacy_level_options:['SELF_ONLY'],creator_nickname:'Creator',creator_username:'creator-a',comment_disabled:false,duet_disabled:true,stitch_disabled:true}):{};
  return {ok:true,json:async()=>data};
 };
 try{await loadSession();await run(posts);}finally{resetSession();globalThis.fetch=oldFetch;}
}
test('post click sends approved metadata and rights confirmation once under concurrent clicks',async()=>{
 await session(async posts=>{const ui=rowFixture();await Promise.all([handlePipelineClick(ui.event),handlePipelineClick(ui.event)]);assert.equal(posts.length,1);assert.deepEqual(posts[0],{clipId:clip.id,platform:'facebook',options:{title:'Approved <title>',caption:'Approved caption',rightsAccepted:true}});assert.match(ui.output.textContent,/Facebook.*prepared/i);});
});
test('stale rows and unready workers cannot publish',async()=>{
 for(const state of [{...workspace(),ready:[]},{...workspace(),workerConnected:false}])await session(async posts=>{const ui=rowFixture();await handlePipelineClick(ui.event);assert.equal(posts.length,0);assert.ok(ui.output.textContent.length>0);},{state});
});
test('Post all sends only connected destinations without prior publication attempts',async()=>{
 const state={...workspace(),publications:[{clipId:clip.id,platform:'tiktok',status:'unknown'}]};
 await session(async posts=>{const ui=rowFixture('all');await handlePipelineClick(ui.event);assert.deepEqual(posts.map(p=>p.platform),['instagram','facebook']);assert.match(ui.output.textContent,/Instagram.*Facebook/i);},{state});
});
test('an account change during Post all stops later destination requests',async()=>{
 await session(async posts=>{const ui=rowFixture('all');await handlePipelineClick(ui.event);assert.equal(posts.length,1);},{state:{...workspace(),publications:[{clipId:clip.id,platform:'tiktok',status:'published'}]},onPost:()=>resetSession()});
});
test('TikTok click loads creator choices without posting or preselecting privacy',async()=>{
 await session(async posts=>{
  const ui=rowFixture('tiktok'),fields=ui.row.querySelector('[data-tiktok-fields]');
  const privacy={value:'',options:[],replaceChildren(...values){this.options=values;this.value=values[0].value;}},creator={textContent:''},inputs={disableComment:{},disableDuet:{},disableStitch:{}};
  fields.querySelector=selector=>selector==='[name="privacy"]'?privacy:selector==='[data-tiktok-creator]'?creator:inputs[selector.match(/name="(.+)"/)[1]];
  const oldOption=globalThis.Option;globalThis.Option=class{constructor(text,value){this.text=text;this.value=value;}};
  try{await handlePipelineClick(ui.event);assert.equal(posts.length,0);assert.equal(fields.hidden,false);assert.equal(privacy.value,'');assert.match(creator.textContent,/Creator/);assert.equal(inputs.disableComment.checked,false);assert.equal(inputs.disableDuet.disabled,true);
   privacy.value='SELF_ONLY';await handlePipelineClick(ui.event);assert.equal(posts.length,1);assert.deepEqual(posts[0].options,{title:'Approved <title>',caption:'Approved caption',rightsAccepted:true,privacy:'SELF_ONLY',disableComment:false,disableDuet:true,disableStitch:true});
  }finally{globalThis.Option=oldOption;}
 });
});
test('Post all reports partial failure and does not retry unknown attempts',async()=>{
 let seen=0;
 await session(async posts=>{const ui=rowFixture('all');await handlePipelineClick(ui.event);assert.equal(posts.length,2);assert.match(ui.output.textContent,/Instagram.*prepared/);assert.match(ui.output.textContent,/Facebook.*provider unavailable/);},{state:{...workspace(),publications:[{clipId:clip.id,platform:'tiktok',status:'unknown'}]},onPost:()=>{if(++seen===2)throw Error('provider unavailable');}});
});
test('a prepared post moves the clip to delivery while other destination actions remain available',()=>{
 const html=renderPublishing(undefined,{...workspace(),publications:[{id:'d'.repeat(32),clipId:clip.id,platform:'facebook',status:'prepared'}]},connections);
 assert.match(html,/Ready to post <span>0/);assert.doesNotMatch(html,/Delivery in progress/);assert.match(html,/Download logs bundle/);assert.match(html,/data-publish-platform="instagram" title=/);assert.match(html,/data-publish-platform="facebook" disabled/);
});
test('a failed initialization cannot resend the same destination from a repeated click',async()=>{
 await session(async posts=>{const ui=rowFixture();await handlePipelineClick(ui.event);await handlePipelineClick(ui.event);assert.equal(posts.length,1);assert.match(ui.output.textContent,/status/i);},{onPost:()=>{throw Error('response lost');}});
});
import {loadPublishingConnections} from '../frontend/js/controllers/publishing-controller.js';
import {loadPipeline} from '../frontend/js/controllers/pipeline-controller.js';
test('a destination changed since display requires reviewing it before publication',async()=>{
 let checks=0;
 const links=()=>({platforms:connections.platforms.map(p=>({...p,accountName:p.id==='facebook'&&++checks>1?'New Page':p.accountName}))});
 await session(async posts=>{await loadPublishingConnections();const ui=rowFixture();await handlePipelineClick(ui.event);assert.equal(posts.length,0);assert.match(ui.output.textContent,/destination changed/i);},{links});
});
test('background publishing refresh preserves required choices and in-flight posting rows',async()=>{
 await session(async()=>{for(const active of ['privacy','posting']){let replaced=false;const page={matches:selector=>selector==='.publishing-page',isConnected:true,querySelector:selector=>selector.includes('[data-publish-busy]')?{active}:null,set outerHTML(value){replaced=true;}};await loadPipeline({querySelector:()=>page});assert.equal(replaced,false);}});
});


test('malformed or mismatched publication responses stay uncertain and cannot fabricate delivery',async()=>{
 for(const result of [{id:'bad',clipId:clip.id,platform:'facebook',status:'published'},{id:'d'.repeat(32),clipId:'e'.repeat(32),platform:'facebook',status:'published'},{id:'d'.repeat(32),clipId:clip.id,platform:'instagram',status:'prepared'},{id:'d'.repeat(32),clipId:clip.id,platform:'facebook',status:'invented'}])await session(async posts=>{const ui=rowFixture();await handlePipelineClick(ui.event);await handlePipelineClick(ui.event);assert.equal(posts.length,1);assert.match(ui.output.textContent,/status/i);assert.ok(!ui.output.textContent.includes('upload prepared'));const html=renderPublishing();assert.match(html,/data-delivery-status="unknown"/);assert.ok(!html.includes('data-delivery-status="published"'));},{onPost:()=>result});
});

function tikTokFixture(){
 const ui=rowFixture('tiktok'),fields=ui.row.querySelector('[data-tiktok-fields]'),privacy={value:'',replaceChildren(...values){this.value=values[0].value;}},creator={textContent:''},inputs={disableComment:{},disableDuet:{},disableStitch:{}};
 fields.querySelector=selector=>selector==='[name="privacy"]'?privacy:selector==='[data-tiktok-creator]'?creator:inputs[selector.match(/name="(.+)"/)[1]];
 return {...ui,fields,privacy,creator};
}
test('open creator choices cannot cross a provider change hidden by polling and the same display name',async()=>{
 let username='creator-a';
 await session(async posts=>{
  const ui=tikTokFixture(),oldOption=globalThis.Option;globalThis.Option=class{constructor(text,value){this.text=text;this.value=value;}};
  try{await handlePipelineClick(ui.event);ui.privacy.value='SELF_ONLY';username='creator-b';
   const page={matches:selector=>selector==='.publishing-page',isConnected:true,querySelector:selector=>selector.includes('[data-publish-busy]')?ui.fields:null,querySelectorAll:()=>[ui.fields]};
   await loadPipeline({querySelector:()=>page});await handlePipelineClick(ui.event);assert.equal(posts.length,0);assert.equal(ui.privacy.value,'');assert.match(ui.output.textContent,/changed|Choose TikTok visibility/i);
   ui.privacy.value='SELF_ONLY';await handlePipelineClick(ui.event);assert.equal(posts.length,1);
  }finally{globalThis.Option=oldOption;}
 },{settings:()=>({creator_username:username,creator_nickname:'Same Name',privacy_level_options:['SELF_ONLY'],comment_disabled:false,duet_disabled:true,stitch_disabled:true})});
});
test('polling clears visible TikTok choices when the connected destination name changes',async()=>{
 let name='Creator A';
 await session(async posts=>{
  const ui=tikTokFixture(),oldOption=globalThis.Option;globalThis.Option=class{constructor(text,value){this.text=text;this.value=value;}};
  try{await handlePipelineClick(ui.event);ui.privacy.value='SELF_ONLY';name='Creator B';
   const page={matches:selector=>selector==='.publishing-page',isConnected:true,querySelector:selector=>selector.includes('[data-publish-busy]')?ui.fields:null,querySelectorAll:()=>[ui.fields]};
   await loadPipeline({querySelector:()=>page});assert.equal(ui.privacy.value,'');assert.equal(ui.fields.dataset.creatorStale,'true');await handlePipelineClick(ui.event);assert.equal(posts.length,0);
  }finally{globalThis.Option=oldOption;}
 },{links:()=>({platforms:connections.platforms.map(p=>({...p,accountName:p.id==='tiktok'?name:p.accountName}))})});
});
