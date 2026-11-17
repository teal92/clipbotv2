const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const script=fs.readFileSync(process.argv[2],'utf8');
const elements=new Map();
function element(){return {textContent:'',className:'',disabled:false,open:true,value:''};}
for(const key of ['#status','#pair-result','#connection','#connection-card','#pair-summary','details','#cpu','#ram','#disk','#readiness'])elements.set(key,element());
const button=element(),code=element();
let submit,resolvePair,pairCalls=0,paired=false,failure=false;
const form={querySelector:q=>q==='button'?button:code,reportValidity:()=>true,addEventListener:(_,fn)=>submit=fn};
elements.set('form',form);elements.set('meta[name=csrf]',{content:'csrf-fixture'});
const context=vm.createContext({document:{querySelector:q=>elements.get(q)},setInterval:()=>{},Number,Error,JSON,
 fetch:async(path,options)=>{
  if(path==='/status')return {ok:true,json:async()=>({paired,message:'<img src=x onerror=alert(1)>',metrics:{cpuPercent:12.6,memoryPercent:43,freeDiskBytes:10737418240},tools:{ffmpeg:true}})};
  pairCalls++;assert.equal(options.headers['X-CSRF-Token'],'csrf-fixture');assert.deepEqual(Object.keys(JSON.parse(options.body)),['code']);
  return new Promise(resolve=>resolvePair=()=>resolve({ok:!failure,json:async()=>failure?{detail:'Code expired. Generate a new code.'}:{message:'Connected'}}));
 }});
const flush=()=>new Promise(resolve=>setImmediate(resolve));
(async()=>{
 vm.runInContext(script,context);await flush();
 assert.equal(elements.get('#cpu').textContent,'13%');assert.equal(elements.get('#disk').textContent,'10 GB free');
 assert.equal(elements.get('#status').textContent,'<img src=x onerror=alert(1)>');
 code.value='one-time-code-fixture';const first=submit({preventDefault(){}});await flush();
 assert.equal(code.value,'');assert.equal(button.disabled,true);assert.match(button.textContent,/Connecting/);
 await submit({preventDefault(){}});assert.equal(pairCalls,1);
 paired=true;resolvePair();await first;
 assert.equal(button.disabled,false);assert.equal(elements.get('details').open,false);assert.match(elements.get('#pair-result').textContent,/Computer connected/);
 failure=true;code.value='another-code-fixture';const second=submit({preventDefault(){}});await flush();resolvePair();await second;
 assert.match(elements.get('#pair-result').textContent,/Code expired/);assert.equal(button.disabled,false);
 console.log('Pairing script: readable health, text-only status, cleared codes, CSRF, duplicate prevention, success and failure passed');
})().catch(error=>{console.error(error);process.exitCode=1;});
