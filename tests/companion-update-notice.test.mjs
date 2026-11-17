import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {createCompanionUpdateNotifier} from '../frontend/js/controllers/companion-controller.js';
import {renderCompanionSetup} from '../frontend/js/views/companion.js';
const state=()=>({companionVersion:'0.2.8',download:{available:true,version:'0.2.9',sha256:'a'.repeat(64),url:'/api/companion/download',releaseKind:'patch',signed:false,unsignedBeta:true,requiresBetaAcceptance:true}});
test('customer patch notes are valid UTF-8 without replacement characters',()=>{
 const source=new TextDecoder('utf-8',{fatal:true}).decode(readFileSync(new URL('../frontend/js/release-notes.js',import.meta.url)));
 assert.ok(source.includes('What’s new')&&source.includes('Kick’s'));
});
function fixture(){const dialog={open:false,innerHTML:'',shows:0,showModal(){this.open=true;this.shows++;}};let blocked=false;return {dialog,root:{querySelector(selector){return selector==='[data-companion-dialog]'?dialog:blocked||dialog.open?{}:null;}},setBlocked(value){blocked=value;}};}
test('available update automatically opens once per visit with readable patch notes and beta protection',()=>{
 const notify=createCompanionUpdateNotifier(),f=fixture(),options={root:f.root,signedIn:true,visible:true};
 assert.equal(notify(state(),options),true);assert.equal(f.dialog.shows,1);
 assert.match(f.dialog.innerHTML,/What.s new/);assert.match(f.dialog.innerHTML,/0\.2\.9/);assert.match(f.dialog.innerHTML,/data-companion-action="accept-beta"/);
 f.dialog.open=false;assert.equal(notify(state(),options),false);assert.equal(f.dialog.shows,1);
 assert.equal(createCompanionUpdateNotifier()(state(),options),true);
});
test('notice defers while hidden, signed out or another dialog is open',()=>{
 const notify=createCompanionUpdateNotifier(),f=fixture();
 assert.equal(notify(state(),{root:f.root,signedIn:false,visible:true}),false);
 assert.equal(notify(state(),{root:f.root,signedIn:true,visible:false}),false);
 f.setBlocked(true);assert.equal(notify(state(),{root:f.root,signedIn:true,visible:true}),false);
 f.setBlocked(false);assert.equal(notify(state(),{root:f.root,signedIn:true,visible:true}),true);
});
test('current, unknown and unavailable versions never produce an update notice',()=>{
 const f=fixture(),options={root:f.root,signedIn:true,visible:true},notify=createCompanionUpdateNotifier();
 for(const value of [{...state(),companionVersion:'0.2.9'},{...state(),companionVersion:null},{...state(),download:{available:false}}])assert.equal(notify(value,options),false);
 assert.equal(f.dialog.shows,0);
});
test('a new installer hash or version can notify after the prior notice was dismissed',()=>{
 const f=fixture(),options={root:f.root,signedIn:true,visible:true},notify=createCompanionUpdateNotifier();
 assert.equal(notify(state(),options),true);f.dialog.open=false;
 const next=state();next.download={...next.download,version:'0.2.10',sha256:'b'.repeat(64)};
 assert.equal(notify(next,options),true);assert.equal(f.dialog.shows,2);
});
test('update patch notes explain actual fixes and escape version text',()=>{
 const html=renderCompanionSetup(state().download,{reason:'update',version:'0.2.8'});
 assert.match(html,/Clip lengths/);assert.match(html,/Kick chat/);assert.match(html,/Bulk phrases/);
 assert.doesNotMatch(renderCompanionSetup({...state().download,version:'<img src=x onerror=alert(1)>'},{reason:'update',version:'0.2.8'}),/<img/);
});
