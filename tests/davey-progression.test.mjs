import test from 'node:test';
import assert from 'node:assert/strict';
import {renderDavey,renderDaveyPreferences} from '../frontend/js/views/davey.js';
import {renderClips} from '../frontend/js/views/clips.js';
import {readDaveyProgression} from '../frontend/js/davey/progression.js';

const settings={personalContext:false,shadowEnabled:false,automatic:false,platforms:[],dailyPostLimit:3,minScore:90,sources:[],rightsAccepted:false};
const state=phase=>({phase,manualDecisions:phase===1?0:100,revision:3,settings,validation:{decisions:25,agreement:92,predictedApprovals:20,approvalPrecision:95},qualified:phase===4,releaseAvailable:true});
test('server phase overrides old local feedback counter and displays actual validation',()=>{
 const html=renderDavey({feedbackCount:0,davey:state(4)});
 assert.match(html,/Phase 4/);assert.match(html,/92%/);assert.match(html,/95%/);assert.match(html,/25/);
 assert.match(renderDavey({feedbackCount:10000}),/Phase 1/);
});
test('consent is always available; validation and automatic options unlock only at their server phases',()=>{
 for(const phase of [1,2,3,4]){
  const html=renderDaveyPreferences({},state(phase));
  assert.match(html,/name="personalContext"/);
  assert.match(html,/reset-davey/);
  assert.equal(html.includes('name="shadowEnabled"'),phase>=3);
  assert.equal(html.includes('name="automatic"'),phase>=4);
  assert.match(html,/notes stay on your computer/);
 }
 assert.match(renderDaveyPreferences({}, {...state(2),settings:{...settings,automatic:true}}),/name="automatic"/); // pause remains available after eligibility loss
});
test('saved controls are escaped and TikTok stays user confirmed',()=>{
 const html=renderDaveyPreferences({}, {...state(4),settings:{...settings,sources:[{platform:'twitch',login:'"><script>bad</script>'}]}});
 assert.doesNotMatch(html,/<script>/);assert.match(html,/TikTok.*confirm/);
 assert.match(html,/name="dailyPostLimit"/);assert.match(html,/max="100"/);
});
test('clips distinguish actual personalized context from pre-decision prediction',()=>{
 const html=renderClips({candidates:[{id:'a',title:'Moment',daveyPrediction:'approve',personalContextUsed:true}],reviews:[]});
 assert.match(html,/Davey predicts: approve/);assert.match(html,/Personal reason counts used/);
});
test('control submission preserves revision, supports Kick hyphens and cascades revocation',()=>{
 const old=globalThis.FormData;
 const values=new Map([['personalContext','on'],['shadowEnabled','on'],['automatic','on'],['rightsAccepted','on'],['automaticPlatforms',['facebook']],['dailyPostLimit','3'],['minScore','90'],['daveySources','kick:some-channel']]);
 globalThis.FormData=class{has(k){return values.has(k);}get(k){return values.get(k);}getAll(k){return values.get(k)??[];}};
 const form={querySelector:selector=>selector==='[data-davey-preferences]'?{dataset:{progression:JSON.stringify({revision:7,settings})}}:{}};
 try{
  const value=readDaveyProgression(form);assert.equal(value.revision,7);assert.equal(value.settings.automatic,true);assert.deepEqual(value.settings.sources,[{platform:'kick',login:'some-channel'}]);
  values.delete('personalContext');assert.equal(readDaveyProgression(form).settings.automatic,false);assert.equal(readDaveyProgression(form).settings.shadowEnabled,false);
  values.set('daveySources','kick:../../run');assert.throws(()=>readDaveyProgression(form),/one source per line/);
 }finally{globalThis.FormData=old;}
});
