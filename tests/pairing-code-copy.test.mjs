import test from 'node:test';
import assert from 'node:assert/strict';
import {mountPairingCode} from '../frontend/js/pairing-code.js';
const code='private-sample-code-1234567890';
function fixture(){
 let click;const output={textContent:''},manual={hidden:true},raw={textContent:''};
 const button={textContent:'Copy code',disabled:false,addEventListener(name,handler){click=handler;}};
 const host={isConnected:true,innerHTML:'',querySelector(selector){return {'[data-copy-pairing-code]':button,'[data-pairing-copy-status]':output,'[data-manual-pairing]':manual,'[data-manual-pairing-code]':raw}[selector];}};
 return {host,button,output,manual,raw,click:()=>click()};
}
test('code is copied only on click and confirmed without displaying it',async()=>{
 const f=fixture(),writes=[];mountPairingCode(f.host,code,{clipboard:{writeText:async value=>writes.push(value)},scope:()=>1,now:()=>1000});
 assert.equal(writes.length,0);assert.ok(!f.host.innerHTML.includes(code));
 await f.click();assert.deepEqual(writes,[code]);assert.equal(f.button.textContent,'Copied');assert.match(f.output.textContent,/copied/i);assert.equal(f.raw.textContent,'');
});
test('clipboard refusal gives a safe manual fallback without HTML interpolation',async()=>{
 const f=fixture(),value='<img src=x onerror=alert(1)>';
 mountPairingCode(f.host,value,{clipboard:{writeText:async()=>{throw Error('denied');}},scope:()=>1});
 await f.click();assert.equal(f.manual.hidden,false);assert.equal(f.raw.textContent,value);assert.ok(!f.host.innerHTML.includes(value));assert.equal(f.button.disabled,false);
});
test('expired and previous-session buttons never copy private codes',async()=>{
 for(const kind of ['expired','signedout','detached']){
  const f=fixture();let session=1,clock=0,calls=0;
  mountPairingCode(f.host,code,{clipboard:{writeText:async()=>calls++},scope:()=>session,now:()=>clock});
  if(kind==='expired')clock=600001;if(kind==='signedout')session=2;if(kind==='detached')f.host.isConnected=false;
  await f.click();assert.equal(calls,0);assert.equal(f.raw.textContent,'');
 }
});
test('a late clipboard failure cannot reveal a code after logout',async()=>{
 const f=fixture();let session=1,reject;
 mountPairingCode(f.host,code,{clipboard:{writeText:()=>new Promise((resolve,no)=>{reject=no;})},scope:()=>session});
 const pending=f.click();session=2;reject(Error('denied'));await pending;assert.equal(f.raw.textContent,'');assert.equal(f.manual.hidden,true);
});
