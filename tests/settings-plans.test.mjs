import test from 'node:test';
import assert from 'node:assert/strict';
import {getSettings,saveSettings,DEFAULT_SETTINGS} from '../frontend/js/settings-state.js';
import {renderSettings} from '../frontend/js/views/settings.js';
import {renderAccount} from '../frontend/js/views/account.js';
const accountHtml=()=>renderAccount({user:{name:'Customer',email:'customer@example.com',username:'customer',avatar:''},plan:{name:'No active plan',coverage:null},billing:{connected:false,message:'Billing is not connected.'}},{settingsHtml:renderSettings()});
import {renderLogs,renderLogEntries} from '../frontend/js/views/logs.js';
import {PLANS,savePlanInterest,getPlanInterest,saveCustomPlan,getCustomPlan,estimateReviewCost} from '../frontend/js/subscription-plans.js';
const store=()=>{const data=new Map();return {getItem:k=>data.get(k)??null,setItem:(k,v)=>data.set(k,v)};};
test('workspace settings remain in Account and billing has its own section',()=>{
 const settings=renderSettings(),account=accountHtml();
 assert.ok(!/<(?:input|textarea)\b/i.test(settings));assert.ok(!settings.includes('name="usagePreset"'));
 assert.ok(settings.includes('Davey Preferences'));assert.ok(account.includes('password hashes'));assert.ok(settings.includes('Identity must be verified'));
 assert.ok(!settings.includes('plan-grid'));assert.ok(account.includes('Plans &amp; Billing'));
 assert.ok(account.includes('role="tablist"'));assert.ok(account.includes('data-account-panel="billing"'));
 for(const section of ['general','billing','profile'])assert.ok(account.includes(`data-account-tab="${section}"`));
});
test('only allowlisted presets can be saved and legacy settings recover safely',()=>{
 const storage=store();assert.equal(getSettings(storage).usagePreset,'paused');
 assert.equal(saveSettings({usagePreset:'light',mode:'review'},storage).ok,true);
 assert.equal(getSettings(storage).dailyBudget,0.25);
 assert.equal(saveSettings({usagePreset:'custom',mode:'review'},storage).ok,false);
 assert.equal(saveSettings({...DEFAULT_SETTINGS,dailyBudget:999},storage).ok,false);
 storage.setItem('clipbot-settings-v1',JSON.stringify({model:'custom',dailyBudget:1000}));
 assert.equal(getSettings(storage).usagePreset,'paused');
});
test('exactly four capped proposals, with interest separate from a subscription',()=>{
 assert.equal(PLANS.length,4);
 assert.deepEqual(PLANS.map(plan=>plan.monthlyPrice),[7,25,60,null]);
 assert.deepEqual(PLANS.slice(0,3).map(plan=>plan.sources),[6,12,30]);assert.equal(PLANS[1].streamerFavorites,3);assert.equal(PLANS[2].categoryFavorites,10);
 const storage=store();assert.equal(savePlanInterest('creator',storage).ok,true);assert.equal(getPlanInterest(storage),'creator');assert.equal(savePlanInterest('fake',storage).ok,false);
});
test('debug log includes successes and warnings and explains errors plainly',()=>{
 const html=renderLogs([{level:'info',source:'ui',message:'Secret success text',createdAt:new Date().toISOString()},{level:'warning',source:'service',message:'Warning text',createdAt:new Date().toISOString()},{level:'error',source:'service',message:'ECONNREFUSED',createdAt:new Date().toISOString()}]);
 assert.ok(html.includes('Secret success text'));assert.ok(html.includes('Warning text'));
 assert.ok(html.includes('ClipBot could not reach the server'));assert.ok(html.includes('data-log-level'));
 assert.ok(renderLogEntries([]).includes('No activity recorded'));
 const hostile=renderLogEntries([{level:'error',source:'davey',message:'<script>alert(1)</script>',createdAt:new Date().toISOString()}]);assert.ok(!hostile.includes('<script>'));
});

test('routine events remain bounded alongside error diagnostics',async()=>{
 const {appendActivity,getActivity}=await import('../frontend/js/activity.js');
 const storage=store();appendActivity({level:'error',source:'service',message:'Keep this failure'},storage);
 for(let i=0;i<300;i++)appendActivity({level:'info',source:'ui',message:'Success'},storage);
 assert.equal(getActivity(storage).length,200);assert.equal(getActivity(storage).at(-1).message,'Success');
});
test('account sections toggle the visible panel and selected state',async()=>{
 const {selectAccountSection}=await import('../frontend/js/controllers/account-profile-controller.js');
 const tabs=['general','billing','profile'].map(name=>({dataset:{accountTab:name},classList:{toggle(_name,value){this.active=value;}},setAttribute(_name,value){this.selected=value;}}));
 const panels=tabs.map(tab=>({dataset:{accountPanel:tab.dataset.accountTab},hidden:tab.dataset.accountTab!=='general'}));
 const page={querySelectorAll(selector){return selector.includes('role="tab"')?tabs:panels;}};
 const saved=globalThis.document;globalThis.document={querySelector:()=>page};
 try{
  selectAccountSection('billing');assert.equal(panels[1].hidden,false);assert.equal(panels[0].hidden,true);assert.equal(tabs[1].selected,'true');assert.equal(tabs[1].tabIndex,0);assert.equal(tabs[0].tabIndex,-1);
  assert.equal(selectAccountSection('settings'),false);assert.equal(panels[1].hidden,false);
  assert.equal(selectAccountSection('untrusted'),false);
 }finally{globalThis.document=saved;}
});

test('form submission saves presets and plan interest and reports storage failure',async()=>{
 const {handleWorkspaceSubmit}=await import('../frontend/js/controllers/workspace-controller.js');
 const storage=store();globalThis.localStorage=storage;
 function submit(kind,values){const output={textContent:''};const form={dataset:{workspaceForm:kind},elements:Object.fromEntries(Object.entries(values).map(([key,value])=>[key,{value}])),querySelector:()=>output,closest:()=>({})};let prevented=false;handleWorkspaceSubmit({target:{closest:()=>form},preventDefault(){prevented=true;}});assert.equal(prevented,true);return output.textContent;}
 try{
  assert.ok(submit('settings',{usagePreset:'light',mode:'review'}).includes('Preferences saved'));
  assert.equal(getSettings(storage).usagePreset,'light');
  assert.ok(submit('plan-interest',{proposedPlan:'pro'}).includes('No subscription was purchased'));
  assert.equal(getPlanInterest(storage),'pro');
  globalThis.localStorage={getItem(){return null;},setItem(){throw Error('blocked');}};
  assert.ok(submit('plan-interest',{proposedPlan:'creator'}).includes('not saved'));
 }finally{delete globalThis.localStorage;}
});

test('hybrid plans never advertise cloud media storage or transfer',()=>{
 const html=accountHtml();
 assert.ok(!html.includes('GB clip storage'));assert.ok(!html.includes('GB monthly media transfer'));
 assert.ok(html.includes('local worker'));assert.ok(html.indexOf('Compare plans')<html.indexOf('Included Usage and Limits'));
 for(const plan of PLANS){assert.ok(!Object.hasOwn(plan,'storageGB'));assert.ok(!Object.hasOwn(plan,'transferGB'));assert.ok(plan.sources>0||plan.id==='custom');}
});

test('Patreon price applies only to Starter and needs verification',()=>{
 assert.ok(PLANS.every(plan=>plan.patreonPrice===undefined));assert.equal(PLANS[0].monthlyPrice,7);
 assert.ok(!accountHtml().includes('Patreon'));
});


test('hybrid explanation is available below the cards and accurately distinguishes Claude',()=>{
 const html=accountHtml();const cards=html.split('<div class="plan-grid">')[1].split('</fieldset>')[0];
 assert.ok(!cards.includes('Video and audio'));assert.ok(!cards.includes('Local editing and rendering'));
 assert.ok(html.includes("Anthropic's servers"));assert.ok(html.includes('candidate reviews per day'));
 assert.ok(html.includes('120 reviews/day and 3,600/month'));
});
test('custom drafts validate manual scaling without granting entitlements',()=>{
 const storage=store();const config={dailyReviews:60,scouts:36,streamerFavorites:12,categoryFavorites:12};
 assert.equal(saveCustomPlan(config,storage).ok,true);assert.deepEqual(getCustomPlan(storage),config);
 for(const changes of [{dailyReviews:-1},{scouts:-1},{scouts:2.5},{streamerFavorites:1000},{dailyReviews:Infinity}])assert.equal(saveCustomPlan({...config,...changes},storage).ok,false);
 assert.equal(estimateReviewCost(450),1.35);assert.equal(estimateReviewCost(1350),4.05);
});
