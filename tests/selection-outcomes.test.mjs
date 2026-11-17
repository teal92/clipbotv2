import test from 'node:test';
import assert from 'node:assert/strict';
import {renderProcessing} from '../frontend/js/views/processing.js';
import {clipWorkflowCounts,renderQueueBoard} from '../frontend/js/views/workflow.js';
import {renderLogEntries} from '../frontend/js/views/logs.js';

const job=(id,errorCode)=>({id,stage:'failed',errorCode,source:{login:id,platform:'twitch'}});
test('normal selection outcomes have separate counts and stay outside processing failures',()=>{
 const html=renderProcessing({pipelineJobs:[job('no-moment','analysis_no_moment'),job('score','analysis_below_threshold'),job('length','analysis_length_settings'),job('legacy','not_selected'),job('broken','processing_failed')]});
 assert.match(html,/No moment found[^<]*<[^>]+>1/);
 assert.match(html,/Below score setting[^<]*<[^>]+>1/);
 assert.match(html,/Outside clip length setting[^<]*<[^>]+>1/);
 assert.match(html,/Processing error[^<]*<[^>]+>1/);
 assert.match(html,/Recent failures and stopped jobs \(1\)/);
 assert.match(html,/Earlier selection outcome/);
 const failureHistory=html.split('Recent failures and stopped jobs')[1];
 assert.match(failureHistory,/broken/);assert.doesNotMatch(failureHistory,/no-moment|legacy/);
});
test('completed non-selection windows count as collected without entering review',()=>{
 assert.deepEqual(clipWorkflowCounts(['analysis_no_moment','analysis_below_threshold','analysis_length_settings','not_selected'].map(code=>job(code,code))),{collected:4,processing:0,review:0});
});
test('normal terminal queue rows show outcome labels instead of failed status',()=>{
 const html=renderQueueBoard([['history','Outcomes',['failed']]],[job('<creator>','analysis_below_threshold')]);
 assert.match(html,/Below score setting/);assert.doesNotMatch(html,/middot; failed/);assert.doesNotMatch(html,/<creator>/);assert.match(html,/&lt;creator&gt;/);
});
test('selection diagnostics explain outcomes even when older events called them errors',()=>{
 for(const [code,label] of [['analysis_no_moment','No moment found'],['analysis_below_threshold','Below score setting'],['analysis_length_settings','Outside clip length setting'],['not_selected','Earlier selection outcome']]){
  const html=renderLogEntries([{id:code,source:'processing',level:'error',message:`Worker processing stage updated (${code})`,createdAt:'2026-10-12T00:00:00Z'}]);
  assert.match(html,new RegExp(label));assert.match(html,/diagnostic-info/);assert.doesNotMatch(html,/could not be processed|retry the clip/);
 }
});


test('workspace refresh does not synthesize errors for completed selection outcomes',async()=>{
 const {refreshWorkspace,resetSession}=await import('../frontend/js/service-state.js');
 const {getActivity}=await import('../frontend/js/activity.js');
 const savedFetch=globalThis.fetch,savedStorage=globalThis.localStorage;
 const values=new Map();globalThis.localStorage={getItem:key=>values.get(key)??null,setItem:(key,value)=>values.set(key,value)};
 globalThis.fetch=async path=>({ok:true,json:async()=>path==='/api/account'?{user:{id:'outcome-test'},csrfToken:'csrf'}:path==='/api/workspace'?{pipelineJobs:[job('normal','analysis_below_threshold'),job('broken','processing_failed')]}:{}});
 try{resetSession();await refreshWorkspace();const entries=getActivity();assert.equal(entries.length,1);assert.equal(entries[0].id,'broken');assert.equal(entries[0].level,'error');await refreshWorkspace();assert.equal(getActivity().length,1);}
 finally{resetSession();globalThis.fetch=savedFetch;globalThis.localStorage=savedStorage;}
});
