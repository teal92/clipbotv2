import test from 'node:test';
import assert from 'node:assert/strict';
import {recommendPlatform,initialDownload,platformLabel} from '../frontend/js/companion-platform.js';
import {renderCompanionSetup} from '../frontend/js/views/companion.js';
import {companionUpdateRequired,createCompanionUpdateNotifier,handleCompanionClick} from '../frontend/js/controllers/companion-controller.js';

test('manual companion check opens downloads regardless of monitoring readiness without starting work',async()=>{
 const originalDocument=globalThis.document,originalFetch=globalThis.fetch;
 const dialog={open:false,innerHTML:'',showModal(){this.open=true;},querySelector(){return null;}};
 const message={textContent:''};
 let state='ready';const requests=[];
 globalThis.document={querySelector(selector){return selector==='[data-companion-dialog]'?dialog:selector==='[data-companion-header-message]'?message:null;}};
 globalThis.fetch=async(path,options)=>{
  requests.push({path,method:options.method??'GET'});
  return {ok:true,json:async()=>({state,errorCode:'coverage_unavailable',companionVersion:'0.2.10',requiredVersion:'0.2.10',download:{available:true,target:'windows-x86_64',url:'/api/companion/download',version:'0.2.10',sha256:'a'.repeat(64),signed:false}})};
 };
 try{
  for(state of ['ready','running','attention','stopping','offline']){
   dialog.open=false;
   const button={dataset:{companionAction:'check'},disabled:false};
   await handleCompanionClick({target:{closest:()=>button}});
   assert.equal(dialog.open,true,`Downloads must open while ${state}`);
   assert.match(dialog.innerHTML,/Download &amp; install/);
   assert.equal(button.disabled,false);
  }
  assert.ok(requests.every(r=>r.path==='/api/companion/status'&&r.method==='GET'));
 }finally{globalThis.document=originalDocument;globalThis.fetch=originalFetch;}
});

test('Mac browsers require an explicit processor choice',()=>{
 assert.deepEqual(recommendPlatform({platform:'MacIntel',userAgent:'Macintosh Intel Mac OS X'}),{os:'macos',targets:['macos-arm64','macos-x86_64']});
 assert.equal(initialDownload({download:{available:true},downloads:[]},{platform:'MacIntel'}).available,false);
});
test('Linux and Windows recommend supported packages without inventing downloads',()=>{
 assert.deepEqual(recommendPlatform({platform:'Linux x86_64'}),{os:'linux',targets:['linux-x86_64']});
 assert.deepEqual(recommendPlatform({platform:'Win32'}),{os:'windows',targets:['windows-x86_64']});
 assert.deepEqual(recommendPlatform({platform:'iPhone'}),{os:null,targets:[]});
 assert.equal(initialDownload({download:{available:true},downloads:[]},{platform:'Linux x86_64'}).available,false);
});
test('native download labels and warnings match the platform and escape metadata',()=>{
 const html=renderCompanionSetup({available:true,target:'macos-arm64',minimumOS:'14.0',url:'/api/companion/download?target=macos-arm64',version:'0.3.0',signed:false,sha256:'a'.repeat(64)});
 assert.match(html,/Mac — Apple Silicon/);
 assert.match(html,/macOS.*verify|verify.*macOS/);
 assert.match(html,/14\.0/);
 assert.doesNotMatch(html,/Windows cannot verify/);
 const unsafe=renderCompanionSetup({available:true,target:'macos-arm64',minimumOS:'<img src=x>',url:'javascript:alert(1)',version:'0.3.0',signed:true});
 assert.doesNotMatch(unsafe,/<img|href="javascript:/);
});
test('selecting another platform does not imply an installed worker update',()=>{
 assert.equal(companionUpdateRequired({platformTarget:'windows-x86_64',companionVersion:'0.2.10',requiredVersion:'0.2.10',download:{available:true,target:'macos-arm64',version:'0.3.0'}}),false);
 assert.equal(platformLabel('../../private'),'Choose your computer');
});

test('experimental Mac download discloses notarization and pending real desktop acceptance',()=>{
 const html=renderCompanionSetup({available:true,target:'macos-arm64',url:'/api/companion/download?target=macos-arm64',version:'0.3.0-beta.1',signed:false,desktopAcceptancePending:true,requiresBetaAcceptance:true});
 assert.match(html,/not notarized by Apple/);
 assert.match(html,/installation and pairing.*not yet.*verified/i);
 assert.match(html,/data-companion-action="accept-beta"/);
 assert.doesNotMatch(html,/href="\/api\/companion\/download/);
});

test('automatic update acknowledgement cannot reuse a dismissed manual platform choice',async()=>{
 const originalDocument=globalThis.document,originalFetch=globalThis.fetch;
 const download={available:true,target:'windows-x86_64',url:'/api/companion/download',version:'0.2.10',sha256:'a'.repeat(64),signed:false,unsignedBeta:true,requiresBetaAcceptance:true};
 const base={state:'ready',companionVersion:'0.2.9',platformTarget:'windows-x86_64',requiredVersion:'0.2.10',download};
 const mac={...download,target:'macos-arm64',url:'/api/companion/download?target=macos-arm64',version:'0.3.0-beta.1',sha256:'b'.repeat(64)};
 const dialog={open:false,innerHTML:'',showModal(){this.open=true;},querySelector(){return null;}};
 const requests=[];
 globalThis.document={querySelector(selector){return selector==='[data-companion-dialog]'?dialog:selector==='dialog[open]'&&dialog.open?dialog:null;}};
 globalThis.fetch=async(path,options)=>{
  requests.push({path,body:options.body?JSON.parse(options.body):null});
  return {ok:true,json:async()=>path.includes('target=macos-arm64')?{...base,download:mac}:base};
 };
 const click=async(action,target)=>{const button={dataset:{companionAction:action,companionTarget:target},disabled:false};await handleCompanionClick({target:{closest:()=>button}});};
 try{
  await click('check');
  await click('choose-platform','macos-arm64');
  dialog.open=false; // The user closed the prior dialog with Escape.
  assert.equal(createCompanionUpdateNotifier()(base,{root:globalThis.document,signedIn:true,visible:true}),true);
  await click('accept-beta');
  const request=requests.find(r=>r.path==='/api/companion/beta-accept');
  assert.equal(request.body.target,'windows-x86_64');
  assert.equal(request.body.sha256,'a'.repeat(64));
 }finally{globalThis.document=originalDocument;globalThis.fetch=originalFetch;}
});
