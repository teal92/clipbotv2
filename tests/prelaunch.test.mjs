import test from 'node:test';
import assert from 'node:assert/strict';
import {renderDashboard} from '../frontend/js/views/dashboard.js';
import {renderStreamers} from '../frontend/js/views/streamers.js';
import {renderClips} from '../frontend/js/views/clips.js';
import {renderProcessing} from '../frontend/js/views/processing.js';
import {renderDavey} from '../frontend/js/views/davey.js';

test('pipeline pages never seed creators, clips, scores or activity',()=>{
 for(const render of [renderDashboard,renderStreamers,renderClips,renderProcessing]){
  const html=render();
  assert.doesNotMatch(html,/DEMO DATA|StreamerOne|StreamerTwo|Perfect timing|91%|66%/i);
  assert.match(html,/No |Offline|Not connected/i);
 }
});
test('Davey keeps configuration inline and distinguishes evidence from model training',()=>{
 const html=renderDavey();
 assert.doesNotMatch(html,/textarea|demo-badge/);assert.match(html,/data-open-view="streamers"/);
 assert.match(html,/progressbar/);
 assert.match(html,/not.*train|not.*training/i);
 assert.match(html,/data-davey-phase/);assert.match(html,/data-davey-phase-dialog/);
});
test('blocked browser storage never blocks resetting or signing in',async()=>{
 const {resetSession}=await import('../frontend/js/service-state.js');
 Object.defineProperty(globalThis,'localStorage',{configurable:true,get(){throw Error('SecurityError');}});
 try{assert.doesNotThrow(()=>resetSession());}finally{delete globalThis.localStorage;}
});

test('expired account session returns to sign-in instead of trapping logout',async()=>{
 const {connectAccountControls}=await import('../frontend/js/controllers/account-controller.js');
 const previousFetch=globalThis.fetch;let click,shown='';
 globalThis.document={addEventListener(type,callback){if(type==='click')click=callback;},querySelector(){return {textContent:''};}};
 globalThis.fetch=async()=>({ok:false,status:401,json:async()=>({detail:'Sign in to continue.'})});
 try{
  connectAccountControls({showWorkspace(){},showAuth(html){shown=html;},refresh(){}});
  const button={dataset:{accountAction:'logout'},disabled:false};
  await click({target:{closest(selector){return selector==='[data-account-action]'?button:null;}}});
  assert.match(shown,/Welcome back/);
  assert.equal(button.disabled,false);
 }finally{globalThis.fetch=previousFetch;delete globalThis.document;}
});

test('temporary bypass button appears only when development mode is allowed',async()=>{
 const {renderAuth}=await import('../frontend/js/views/auth.js');
 assert.doesNotMatch(renderAuth('signup',false),/data-dev-bypass/);
 assert.match(renderAuth('signup',true),/data-dev-bypass/);
 assert.match(renderAuth('login',true),/Bypass Signup/);
});
