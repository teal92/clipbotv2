import test from 'node:test';
import assert from 'node:assert/strict';
import {refreshWorkspace,resetSession,saveCandidateReview,getWorkspace} from '../frontend/js/service-state.js';
const cap='a'.repeat(64),candidate={id:'clip-1',previewUrl:'http://127.0.0.1:8767/preview/'+cap};
const event={candidate:{id:'clip-1'},user_feedback:{decision:'reject',reasons:['Needs context'],justification:'PRIVATE NOTE'}};
const receipt={candidateId:'clip-1',userId:'person-1',decision:'reject',issuedAt:123,signature:'b'.repeat(64)};
const response=data=>({ok:true,json:async()=>data});
async function withService(run,{preview=candidate.previewUrl,localFail=false,confirmFail=false}={}){
 const original=globalThis.fetch,calls=[];
 resetSession();globalThis.fetch=async(url,options={})=>{
  const body=options.body?JSON.parse(options.body):null;calls.push({url,options,body});
  if(url==='/api/account')return response({user:{id:'person-1'},csrfToken:'csrf'});
  if(url==='/api/workspace')return response({candidates:[{...candidate,previewUrl:preview}],reviews:[]});
  if(url==='/api/reviews')return response({localFeedbackReceipt:receipt});
  if(url.startsWith('http://127.0.0.1:8767/feedback/')){
   if(options.method==='POST'&&((url.endsWith('/confirm')&&confirmFail)||(!url.endsWith('/confirm')&&localFail)))throw Error('offline');
   return response({ok:true,feedback:null});
  }
  return response({});
 };
 try{await refreshWorkspace();calls.length=0;await run(calls);}finally{resetSession();globalThis.fetch=original;}
}
test('private feedback is saved locally before a decision-only cloud review and confirmed receipt',async()=>{
 await withService(async calls=>{
  assert.equal((await saveCandidateReview(event)).ok,true);
  const writes=calls.filter(c=>c.options.method==='POST');
  assert.equal(writes[0].url,'http://127.0.0.1:8767/feedback/'+cap);
  assert.deepEqual(writes[0].body,{candidateId:'clip-1',userId:'person-1',decision:'reject',reasons:['Needs context'],justification:'PRIVATE NOTE'});
  assert.deepEqual(writes[1].body,{candidate_id:'clip-1',decision:'reject',reasons:[],justification:'',localLearning:true});
  assert.equal(writes[2].url,'http://127.0.0.1:8767/feedback/'+cap+'/confirm');assert.deepEqual(writes[2].body,{receipt});
 });
});
test('offline local feedback never falls back to uploading private notes',async()=>{
 await withService(async calls=>{await assert.rejects(saveCandidateReview(event),/local|companion/i);assert.ok(!calls.some(c=>c.url==='/api/reviews'));},{localFail:true});
});
test('unconfirmed local save remains pending after cloud acceptance',async()=>{
 await withService(async calls=>{await assert.rejects(saveCandidateReview(event),/pending/i);assert.equal(calls.filter(c=>c.url==='/api/reviews').length,1);},{confirmFail:true});
});
test('personal notes cannot go to an unowned or unsafe preview URL',async()=>{
 for(const preview of ['https://evil.test/preview/'+cap,'http://user:pass@127.0.0.1:8767/preview/'+cap,'http://127.0.0.1:8767/preview/'+cap+'?key=secret']){
  await withService(async calls=>{await assert.rejects(saveCandidateReview(event),/preview|local|companion/i);assert.ok(!calls.some(c=>c.options.method==='POST'));},{preview});
 }
 await withService(async calls=>{await assert.rejects(saveCandidateReview({...event,candidate:{id:'unowned'}}),/candidate|account/i);assert.equal(calls.length,0);});
});
test('account change during local feedback save prevents cloud write and confirmation',async()=>{
 await withService(async calls=>{
  const existing=globalThis.fetch;globalThis.fetch=async(url,options)=>{const result=await existing(url,options);if(url==='http://127.0.0.1:8767/feedback/'+cap&&options?.method==='POST')resetSession();return result;};
  await assert.rejects(saveCandidateReview(event),/Account changed/);assert.ok(!calls.some(c=>c.url==='/api/reviews'));
 });
});

test('only confirmed matching local notes merge into account reviews',async()=>{
 const original=globalThis.fetch;let local={candidateId:'clip-1',userId:'person-1',decision:'reject',reasons:['Needs context'],justification:'LOCAL PRIVATE',confirmed:true};
 const cloudReview={candidate:{id:'clip-1'},user_feedback:{decision:'reject',reasons:[],justification:''}};
 resetSession();globalThis.fetch=async url=>response(url==='/api/account'?{user:{id:'person-1'}}:url==='/api/workspace'?{candidates:[structuredClone(candidate)],reviews:[structuredClone(cloudReview)]}:url.startsWith('http://127.0.0.1:8767/feedback/')?{feedback:local}:{});
 try{
  await refreshWorkspace();assert.equal(getWorkspace().reviews[0].user_feedback.justification,'LOCAL PRIVATE');assert.equal(getWorkspace().reviews[0].localFeedbackStatus,'confirmed');
  local={...local,confirmed:false};await refreshWorkspace();assert.equal(getWorkspace().reviews[0].user_feedback.justification,'');assert.equal(getWorkspace().candidates[0].localFeedbackPending.justification,'LOCAL PRIVATE');
  local={...local,confirmed:true,userId:'other-person'};await refreshWorkspace();assert.equal(getWorkspace().reviews[0].user_feedback.justification,'');assert.equal(getWorkspace().candidates[0].localFeedbackPending,undefined);
 }finally{resetSession();globalThis.fetch=original;}
});
test('reject without preview sends only decision and clearly reports missing local learning',async()=>{
 await withService(async calls=>{const saved=await saveCandidateReview({...event,user_feedback:{decision:'reject',reasons:[],justification:''}});assert.equal(saved.ok,true);assert.match(saved.notice,/not stored/);assert.equal(calls.filter(c=>c.options.method==='POST').length,1);assert.equal(calls.find(c=>c.options.method==='POST').url,'/api/reviews');},{preview:null});
});
test('account change during cloud confirmation prevents local receipt from crossing accounts',async()=>{
 await withService(async calls=>{
  const existing=globalThis.fetch;globalThis.fetch=async(url,options)=>{const result=await existing(url,options);if(url==='/api/reviews')resetSession();return result;};
  await assert.rejects(saveCandidateReview(event),/Account changed/);assert.ok(!calls.some(c=>c.url.endsWith('/confirm')));
 });
});
import {renderClips,renderDecisionPanel,renderSavedDecision} from '../frontend/js/views/clips.js';
test('pending local notes are visible and restored for a retry without claiming confirmed learning',()=>{
 const feedback={decision:'reject',reasons:['Needs context'],justification:'<private note>'};
 const html=renderClips({candidates:[{...candidate,localFeedbackPending:feedback}],reviews:[]});assert.match(html,/pending on this computer/);
 const panel=renderDecisionPanel('reject',feedback);assert.match(panel,/data-reason="Needs context"[\s\S]{0,20}selected|decision-reason selected[\s\S]{0,100}Needs context/);assert.match(panel,/&lt;private note&gt;/);assert.doesNotMatch(panel,/<private note>/);
 const saved=renderSavedDecision('reject',{localFeedbackStatus:'pending'});assert.match(saved,/pending/);assert.doesNotMatch(saved,/preference evidence/);
});

test('an offline companion is probed once instead of retrying every retained candidate',async()=>{
 const original=globalThis.fetch;let localReads=0;resetSession();
 globalThis.fetch=async url=>{if(url.startsWith('http://127.0.0.1:8767/feedback/')){localReads++;throw Error('offline');}return response(url==='/api/account'?{user:{id:'person-1'}}:url==='/api/workspace'?{candidates:Array.from({length:200},(_,i)=>({...candidate,id:'clip-'+i})),reviews:[]}:{});};
 try{await refreshWorkspace();assert.equal(localReads,1);assert.equal(getWorkspace().candidates.filter(c=>c.localFeedbackUnavailable).length,200);}finally{resetSession();globalThis.fetch=original;}
});

test('a missing older local clip does not hide another candidate personal notes',async()=>{
 const original=globalThis.fetch;let reads=0;resetSession();const second={...candidate,id:'clip-2',previewUrl:'http://127.0.0.1:8767/preview/'+'c'.repeat(64)};
 globalThis.fetch=async url=>{if(url.startsWith('http://127.0.0.1:8767/feedback/')){reads++;return url.endsWith(cap)?{ok:false,status:404,json:async()=>({})}:response({feedback:{candidateId:'clip-2',userId:'person-1',decision:'reject',reasons:['Funny'],justification:'LOCAL',confirmed:true}});}return response(url==='/api/account'?{user:{id:'person-1'}}:url==='/api/workspace'?{candidates:[structuredClone(candidate),second],reviews:[{candidate:{id:'clip-2'},user_feedback:{decision:'reject',reasons:[],justification:''}}]}:{});};
 try{await refreshWorkspace();assert.equal(reads,2);assert.equal(getWorkspace().reviews[0].user_feedback.justification,'LOCAL');}finally{resetSession();globalThis.fetch=original;}
});
