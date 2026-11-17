import test from 'node:test';
import assert from 'node:assert/strict';
import {refreshWorkspace,resetSession,getWorkspace,getAccount} from '../frontend/js/service-state.js';
test('logout discards pending account workspace responses',async()=>{
 const original=globalThis.fetch;const pending=[];
 globalThis.fetch=()=>new Promise(resolve=>pending.push(resolve));
 try{
  const refresh=refreshWorkspace();resetSession();
  for(const resolve of pending)resolve({ok:true,json:async()=>({user:{id:'previous-account'},sources:[{login:'private-source'}]})});
  await refresh.catch(()=>{});
  assert.equal(getAccount(),null);assert.deepEqual(getWorkspace().sources,[]);
 }finally{globalThis.fetch=original;resetSession();}
});
