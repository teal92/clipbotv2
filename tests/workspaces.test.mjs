import test from 'node:test';
import assert from 'node:assert/strict';
import { getSettings, saveSettings, DEFAULT_SETTINGS } from '../frontend/js/settings-state.js';
import { appendActivity, getActivity, clearActivity } from '../frontend/js/activity.js';
import { getLearning, savePreferences, recordReview } from '../frontend/js/davey/learning.js';
import { checkService } from '../frontend/js/runtime.js';
import { renderDavey } from '../frontend/js/views/davey.js';
import { renderLogs } from '../frontend/js/views/logs.js';
import { renderSettings } from '../frontend/js/views/settings.js';
function storage() { const values = new Map(); return { getItem: k => values.get(k) ?? null, setItem: (k,v) => values.set(k,v), removeItem: k => values.delete(k), values }; }
const broken = { getItem() { throw Error('blocked'); }, setItem() { throw Error('blocked'); }, removeItem() { throw Error('blocked'); } };
test('settings recover and save only validated nonsecret fields', () => {
 const store = storage(); assert.deepEqual(getSettings(store), DEFAULT_SETTINGS);
 assert.equal(saveSettings({usagePreset:'balanced',mode:'review',apiKey:'secret'}, store).ok, true);
 assert.equal(getSettings(store).dailyBudget, 0.5); assert.ok(![...store.values.values()].join('').includes('secret'));
 store.values.set('clipbot-settings-v1', '{'); assert.deepEqual(getSettings(store), DEFAULT_SETTINGS);
 for (const change of [{dailyBudget: -1}, {dailyBudget: ''}, {maxTurns: 0}, {maxTurns: 1.2}, {maxOutputTokens: Infinity}, {mode: 'autonomous'}, {model: '  '}, {dailyBudget: null}]) assert.equal(saveSettings({...DEFAULT_SETTINGS,...change}, store).ok, false);
 assert.equal(saveSettings(DEFAULT_SETTINGS, broken).ok, false);
});
test('logs are bounded, redact common credentials, and can be cleared', () => {
 const store = storage();
 appendActivity({level:'error',source:'davey',message:'Bearer abc123 api_key=secret token=xyz sk-ant-api03-abcdef'},store);
 const message = getActivity(store)[0].message;
 for (const secret of ['abc123','secret','xyz','sk-ant-api03-abcdef']) assert.ok(!message.includes(secret));
 for (let i=0;i<205;i++) appendActivity({level:'error',source:'ui',message:String(i)},store);
 assert.equal(getActivity(store).length,200); assert.equal(getActivity(store).at(-1).message,'204');
 assert.equal(clearActivity(store).ok,true); assert.equal(getActivity(store).length,0);
 assert.equal(appendActivity({level:'error',message:'hello'},broken).ok,false);
});
test('preferences persist and duplicate feedback updates instead of multiplying', () => {
 const store=storage(); assert.equal(savePreferences({contentFocus:'Humor',avoidTopics:'Personal information'},store).ok,true);
 const event={ candidate:{id:'one',creator:'Creator',platform:'Twitch',duration:'0:27',category:'Game'}, user_feedback:{decision:'approve',reasons:['Funny'],justification:'Good payoff'},created_at:new Date().toISOString() };
 assert.equal(recordReview(event,store).ok,true); assert.equal(recordReview(event,store).ok,true);
 assert.equal(getLearning(store).reviews.length,1); assert.equal(getLearning(store).preferences.contentFocus,'Humor');
 assert.equal(recordReview({...event,user_feedback:{decision:'invalid'}},store).ok,false);
 assert.equal(savePreferences({contentFocus:'x'.repeat(501),avoidTopics:''},store).ok,false);
 assert.equal(recordReview(event,broken).ok,false);
});
test('workspace views escape user text and never claim AI is running', () => {
 const hostile='<script>alert(1)</script>';
 const davey=renderDavey({preferences:{focus:hostile,avoid:'personal',usagePreset:'paused'},feedbackCount:0,aiConfigured:false});
 const logs=renderLogs([{id:'a',level:'error',source:'ui',message:hostile,createdAt:new Date().toISOString()}]);
 const settings=renderSettings({...DEFAULT_SETTINGS,model:hostile});
 for(const html of [davey,logs,settings]) assert.ok(!html.includes('<script>'));
 assert.ok(logs.includes('&lt;script&gt;'));assert.ok(!davey.includes(hostile));
 assert.ok(davey.includes('Recorded feedback measures collected evidence')); assert.ok(settings.includes('Policies and your rights'));assert.ok(settings.includes('Never put passwords, API keys or sensitive personal information in reports'));assert.ok(settings.includes('Identity must be verified')); assert.ok(logs.includes('Error Log'));
});
test('health check rejects unavailable and unrelated services', async () => {
 assert.equal((await checkService(async()=>{throw Error('offline');})).connected,false);
 assert.equal((await checkService(async()=>({ok:true,json:async()=>({hello:'world'})}))).connected,false);
 assert.equal((await checkService(async()=>({ok:true,json:async()=>({service:'clipbot',version:1,worker:{connected:false},davey:{configured:true},budget:{enforced:true}})}))).connected,true);
});

test('log filters combine search, source, and severity', async () => {
 const {filterActivity}=await import('../frontend/js/activity.js');
 const entries=[{level:'warning',source:'service',message:'Unavailable'},{level:'info',source:'settings',message:'Saved'}];
 assert.deepEqual(filterActivity(entries,{level:'warning',source:'service',search:'UNAVAILABLE'}),[entries[0]]);
 assert.deepEqual(filterActivity(entries,{level:'error'}),[]);
});
test('live event feed validates entries and closes on disconnect', async () => {
 const {connectActivityFeed}=await import('../frontend/js/runtime.js');
 const events=[];let fake;
 class Source { constructor(url){assert.equal(url,'/api/events');fake=this;} close(){this.closed=true;} }
 const stop=connectActivityFeed(entry=>events.push(entry),()=>{},Source);
 fake.onmessage({data:JSON.stringify({level:'info',source:'davey',message:'Analyzed candidate'})});
 fake.onmessage({data:'{'}); fake.onmessage({data:JSON.stringify({level:'invalid',source:'davey',message:'Bad'})});
 assert.equal(events.length,1);
 fake.onerror(); assert.equal(fake.closed,true);stop();
});
test('quoted credentials are redacted and model field rejects accidental keys', async () => {
 const {redact}=await import('../frontend/js/activity.js');
 assert.ok(!redact('{"api_key":"abc123","token":"xyz"}').includes('abc123'));
 assert.ok(!redact('{"api_key":"abc123","token":"xyz"}').includes('xyz'));
 assert.equal(saveSettings({...DEFAULT_SETTINGS,model:'sk-ant-api03-private'},storage()).ok,false);
});

test('Clips restores saved decisions after navigation', async () => {
 const {renderClips}=await import('../frontend/js/views/clips.js');
 const store=storage();
 globalThis.localStorage=store;
 try {
  recordReview({candidate:{id:'twitch-xqc-91',creator:'xqc'},user_feedback:{decision:'reject',reasons:['Needs context']}},store);
  const html=renderClips({candidates:[{id:'twitch-xqc-91',creator:'xqc',platform:'Twitch',category:'Game',duration:'0:27'}],reviews:getLearning(store).reviews});
  assert.ok(html.includes('data-review-status="reject"'));
  assert.ok(html.includes('data-clip-action="re-review"'));
 } finally {delete globalThis.localStorage;}
});
