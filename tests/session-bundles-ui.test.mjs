import test from 'node:test';
import assert from 'node:assert/strict';
import * as logs from '../frontend/js/views/logs.js';
import {refreshLogs,stopWorkspaceActivity} from '../frontend/js/controllers/workspace-controller.js';
import {loadSession,resetSession} from '../frontend/js/service-state.js';
const id = n => String(n).padStart(32,'0');
const session = (n,startedAt,state='stopped') => ({id:id(n),startedAt,stoppedAt:state==='running'?null:startedAt,state,configuration:{},droppedEvents:0});
const render = sessions => {
 assert.equal(typeof logs.renderSessionBundles,'function','Logs must expose the real session renderer');
 return logs.renderSessionBundles(sessions);
};

test('session downloads are ordered by start time rather than API order or active state',()=>{
 const input=[session(1,'2026-10-12T10:00:00Z','running'),session(2,'2026-10-12T12:00:00+00:00'),session(3,'2026-10-12T08:00:00-05:00')];
 const html=render(input);
 assert.ok(html.indexOf(`/sessions/${id(3)}`)<html.indexOf(`/sessions/${id(2)}`));
 assert.ok(html.indexOf(`/sessions/${id(2)}`)<html.indexOf(`data-session-id="${id(1)}"`));
 assert.equal((html.match(/session-bundle-latest/g)??[]).length,1);
 assert.equal((html.match(/>Latest</g)??[]).length,1);
 assert.deepEqual(input.map(s=>s.id),[id(1),id(2),id(3)],'Rendering must not mutate server state');
});

test('equal start times prefer the running session and produce one stable latest row',()=>{
 const a=session(2,'2026-10-12T12:00:00Z'),b=session(1,'2026-10-12T12:00:00Z','running');
 const html=render([a,b]);
 assert.ok(html.indexOf(`data-session-id="${id(1)}"`)<html.indexOf(`/sessions/${id(2)}`));
 assert.equal(html,render([b,a]));
 assert.match(html,/Latest/);assert.match(html,/Running/);
});

test('session list retains older downloads and sorts unknown dates last with readable fallback',()=>{
 const html=render([session(9,'not-a-date'),...Array.from({length:7},(_,n)=>session(n+1,`2026-10-${String(n+1).padStart(2,'0')}T12:00:00Z`))]);
 assert.equal((html.match(/ download/g)??[]).length,8);
 assert.ok(html.indexOf(`/sessions/${id(7)}`)<html.indexOf(`/sessions/${id(9)}`));
 assert.match(html,/Start time unavailable/);assert.doesNotMatch(html,/Invalid Date/);
});

test('session rows reject unsafe IDs, deduplicate downloads and render only safe known states',()=>{
 const html=render([session(1,'2026-10-12T12:00:00Z'),session(1,'2026-10-12T12:00:00Z'),{...session(2,'2026-10-11T12:00:00Z'),id:'../private?token=SECRET'},{...session(3,'bad'),state:'<script>SECRET</script>',configuration:{token:'SECRET'}},null]);
 assert.equal((html.match(/ download/g)??[]).length,1);
 assert.doesNotMatch(html,/SECRET|<script>/);assert.match(html,/Unknown state/);
 assert.equal((html.match(/session-bundle-latest/g)??[]).length,1);
});

test('session downloads have descriptive accessible labels and machine-readable valid dates',()=>{
 const html=render([session(1,'2026-10-12T12:00:00Z','running')]);
 assert.match(html,/<li\b/);assert.match(html,/<time datetime="2026-10-12T12:00:00.000Z"/);
 assert.match(html,/disabled[^>]*title="Available after the session ends"/);assert.doesNotMatch(html,/href="\/api\/logs\/sessions/);
 assert.match(logs.renderLogs([]),/data-debug-sessions[^>]*tabindex="0"[^>]*aria-label="Session debugging bundles"/);
});

test('empty and malformed session lists show the monitoring guidance',()=>{
 for(const input of [[],null,{},[{id:'invalid'}]])assert.match(render(input),/No monitoring sessions recorded yet/);
});

for(const outcome of ['success','failure'])test(`account change discards pending session ${outcome} response`,async()=>{
 const priorFetch=globalThis.fetch,priorStorage=globalThis.localStorage;
 const storage=new Map();globalThis.localStorage={getItem:k=>storage.get(k)??null,setItem:(k,v)=>storage.set(k,v),removeItem:k=>storage.delete(k)};
 let release;
 globalThis.fetch=async path=>path==='/api/account'?{ok:true,json:async()=>({user:{id:'session-owner'},csrfToken:'csrf'})}:path==='/api/logs/sessions'?new Promise((resolve,reject)=>{release=outcome==='success'?()=>resolve({ok:true,json:async()=>({sessions:[session(1,'2026-10-12T12:00:00Z')]})}):()=>reject(Error('offline'));}):{ok:true,json:async()=>({events:[],cursor:0})};
 const output={innerHTML:'Current account',textContent:'Current account'},page={isConnected:true,querySelector:q=>q==='[data-debug-sessions]'?output:null};
 try{
  await loadSession();const pending=refreshLogs(page);
  while(!release)await new Promise(resolve=>setImmediate(resolve));
  resetSession();release();await pending;
  assert.equal(output.innerHTML,'Current account');assert.equal(output.textContent,'Current account');
 }finally{stopWorkspaceActivity();resetSession();globalThis.fetch=priorFetch;globalThis.localStorage=priorStorage;}
});
