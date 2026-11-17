import test from 'node:test';
import assert from 'node:assert/strict';
import {appendActivity,getActivity,redact} from '../frontend/js/activity.js';
import {renderLogs,renderLogEntries} from '../frontend/js/views/logs.js';
import * as controller from '../frontend/js/controllers/workspace-controller.js';
const store=()=>{const values=new Map();let writes=0;return {getItem:k=>values.get(k)??null,setItem:(k,v)=>{writes++;values.set(k,v);},get writes(){return writes;}};};

test('pipeline logs retain every severity and deduplicate server event IDs',()=>{
 const storage=store();for(const level of ['debug','info','warning','error'])appendActivity({id:level,level,source:'processing',message:`${level} event`},storage);
 appendActivity({id:'info',level:'info',source:'processing',message:'info event'},storage);
 assert.deepEqual(getActivity(storage).map(v=>v.level),['debug','info','warning','error']);
 assert.match(renderLogs(getActivity(storage)),/debug event/);assert.match(renderLogs(getActivity(storage)),/data-log-level/);
});
test('diagnostic redaction removes signed queries, credentials and private transcripts before console or storage',()=>{
 const storage=store(),output=[],prior=console.debug;console.debug=(...args)=>output.push(args.join(' '));
 try{appendActivity({level:'info',source:'processing',message:'Fetch https://worker.test/media?id=secretID&sig=privateSig transcript="private words" access_token=privateToken'},storage);}
 finally{console.debug=prior;}
 const result=getActivity(storage)[0]?.message??'',printed=output.join(' ');
 for(const secret of ['secretID','privateSig','private words','privateToken']){assert.ok(!result.includes(secret));assert.ok(!printed.includes(secret));}
 assert.match(result,/https:\/\/worker.test\/media/);assert.match(printed,/ClipBot/);
 assert.ok(!redact('{"transcript":"words never log","refresh_token":"private"}').includes('words never log'));
});
test('server refresh imports all levels, retains filters and restores expanded diagnostic details',async()=>{
 const {loadSession,resetSession}=await import('../frontend/js/service-state.js');
 const savedFetch=globalThis.fetch,savedStorage=globalThis.localStorage;globalThis.localStorage=store();const requests=[];
 const previousDetail={dataset:{logId:'render9'},open:true},freshDetail={dataset:{logId:'render9'},open:false};
 const output={innerHTML:'',querySelectorAll:q=>q==='details[open]'?[previousDetail]:[freshDetail],querySelector:()=>null};
 const source={value:'processing'},search={value:'render'},level={value:'info'},status={textContent:''};
 const page={isConnected:true,querySelector:q=>({'[data-log-entries]':output,'[data-log-source]':source,'[data-log-search]':search,'[data-log-level]':level,'[data-workspace-status]':status})[q]??null};
 globalThis.fetch=async path=>{requests.push(path);return {ok:true,json:async()=>path==='/api/account'?{user:{id:'logs-user'},csrfToken:'csrf'}:path.startsWith('/api/logs')?{cursor:9,events:[{id:'render9',level:'info',source:'processing',message:'render completed',createdAt:'2026-10-12T10:00:00Z'},{id:'error8',level:'error',source:'service',message:'connection issue',createdAt:'2026-10-12T10:00:00Z'}]}:{}};};
 try{await loadSession();await controller.refreshLogs(page);assert.ok(requests.some(p=>p.startsWith('/api/logs')));assert.match(output.innerHTML,/render completed/);assert.doesNotMatch(output.innerHTML,/connection issue/);assert.equal(search.value,'render');assert.equal(level.value,'info');assert.equal(getActivity().length,2);assert.equal(freshDetail.open,true);assert.equal(globalThis.localStorage.writes,1);await controller.refreshLogs(page);assert.ok(requests.includes('/api/logs?after=9'));assert.equal(getActivity().length,2);}
 finally{controller.stopWorkspaceActivity();resetSession();globalThis.fetch=savedFetch;globalThis.localStorage=savedStorage;}
});

test('leaving Logs discards pending server responses and prevents private activity from appearing later',async()=>{
 const {loadSession,resetSession}=await import('../frontend/js/service-state.js');
 const savedFetch=globalThis.fetch,savedStorage=globalThis.localStorage;globalThis.localStorage=store();let release;
 globalThis.fetch=async path=>path.startsWith('/api/logs')?new Promise(resolve=>{release=resolve;}):{ok:true,json:async()=>path==='/api/account'?{user:{id:'first-user'},csrfToken:'csrf'}:{}};
 const output={innerHTML:'',querySelectorAll:()=>[]},status={textContent:''},page={isConnected:true,querySelector:q=>q==='[data-log-entries]'?output:q==='[data-workspace-status]'?status:null};
 try{await loadSession();const pending=controller.refreshLogs(page);controller.stopWorkspaceActivity();release({ok:true,json:async()=>({events:[{id:'private1',source:'processing',level:'info',message:'Old session activity'}],cursor:1})});await pending;assert.equal(getActivity().length,0);assert.equal(output.innerHTML,'');}
 finally{controller.stopWorkspaceActivity();resetSession();globalThis.fetch=savedFetch;globalThis.localStorage=savedStorage;}
});


test('analysis details survive browser storage with only safe fields',()=>{
 const storage=store();appendActivity({id:'shape',level:'error',source:'davey',message:'Unreadable data',details:{parseLine:2,outputShape:'plain',transcript:'PRIVATE',parseColumn:true}},storage);
 const entry=getActivity(storage)[0];assert.deepEqual(entry.details,{parseLine:2,outputShape:'plain'});assert.match(renderLogEntries([entry]),/parseLine/);assert.doesNotMatch(renderLogEntries([entry]),/PRIVATE/);
});


test('monitor state and companion version survive diagnostic normalization',()=>{
 const storage=store();appendActivity({id:'monitor',level:'info',source:'scouting',message:'Stream changed',details:{monitorState:'reconnecting',chatStatus:'unavailable',speechStatus:'waiting',companionVersion:'0.2.5-beta',token:'PRIVATE'}},storage);
 assert.deepEqual(getActivity(storage)[0].details,{monitorState:'reconnecting',chatStatus:'unavailable',speechStatus:'waiting',companionVersion:'0.2.5-beta'});
});


test('selection diagnostics retain bounded settings and reject private or invalid values',()=>{
 const storage=store();appendActivity({id:'selection',level:'info',source:'davey',message:'Below score setting',details:{candidateScore:58,scoreThreshold:60,minClipSeconds:15,maxClipSeconds:45,candidateMillis:38000,failureReason:'ambiguous_json',transcript:'PRIVATE',responseChars:true}},storage);
 assert.deepEqual(getActivity(storage)[0].details,{candidateScore:58,scoreThreshold:60,minClipSeconds:15,maxClipSeconds:45,candidateMillis:38000,failureReason:'ambiguous_json'});
});
