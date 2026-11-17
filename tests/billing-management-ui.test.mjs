import test from 'node:test';
import assert from 'node:assert/strict';
import {renderAccount} from '../frontend/js/views/account.js';
import {renderPlanChange} from '../frontend/js/views/billing-changes.js';
const base={user:{name:'customer',email:'customer@example.test'},plan:{name:'Starter',coverage:null},billing:{connected:true,mode:'live',sandbox:false,message:'Billing connected.',portalAvailable:true,subscription:{plan:'starter',status:'active',expires:4102444800}}};
test('live customers see payment management and explicit immediate cancellation instead of sandbox-only instructions',()=>{
 const html=renderAccount(base);
 assert.ok(html.includes('data-billing-portal'));
 assert.ok(html.includes('data-cancel-subscription'));
 assert.ok(html.includes('name="acknowledged"'));
 assert.ok(!html.includes('Cancellation, refunds and extra usage purchases are not available'));
 assert.ok(html.includes('Cancellation ends ClipBot service immediately'));assert.ok(html.includes('no automatic refund'));assert.ok(html.includes('Cancel Subscription Now'));
});
test('live plan changes disclose real payment authorization and do not label live invoices as test payments',()=>{
 const html=renderPlanChange({...base.billing,change:{plan:'creator',status:'payment_pending',paymentUrl:'https://invoice.stripe.com/i/verified',sandbox:false}});
 assert.ok(!html.includes('Sandbox only: no real charges'));
 assert.ok(html.includes('Complete payment'));
 assert.ok(!html.includes('Complete test payment'));
});
test('uncertain cancellation stays visible and cannot be silently presented as success or start another cancellation',()=>{
 const html=renderAccount({...base,billing:{...base.billing,cancellation:{status:'reconciliation_required',effectiveAt:4102444800,sandbox:false}}});
 assert.ok(html.includes('Cancellation needs confirmation'));
 assert.ok(!html.includes('data-cancel-subscription'));
 assert.ok(html.includes('Refresh Billing Status'));
});
import {connectAccountControls} from '../frontend/js/controllers/account-controller.js';
import {loadSession,resetSession} from '../frontend/js/service-state.js';
async function paymentClick({kind='checkout',mode='live',result={url:'https://checkout.stripe.com/c/pay/live',sandbox:false}}={}){
 const saved={document:globalThis.document,fetch:globalThis.fetch,window:globalThis.window};const handlers={},assigned=[],requests=[],status={textContent:''};
 const button={disabled:false,dataset:{checkoutPlan:'starter'}};
 globalThis.document={querySelectorAll:()=>[],addEventListener:(kind,fn)=>{handlers[kind]=fn;},querySelector:()=>status};
 globalThis.window={location:{assign:value=>assigned.push(value)}};
 globalThis.fetch=async(path,options)=>{requests.push(path);return {ok:true,status:200,json:async()=>path==='/api/account'?{...base,user:{...base.user,id:'sample-user'},csrfToken:'sample-csrf',billing:{...base.billing,mode,sandbox:mode==='test'}}:path.startsWith('/api/billing/')?result:path==='/api/workspace'?{candidates:[],reviews:[],sources:[],pipelineJobs:[]}:{}};};
 try{
  resetSession();await loadSession();requests.length=0;
  connectAccountControls({showWorkspace:()=>{},showAuth:()=>{},refresh:()=>{}});
  await handlers.click({target:{closest:selector=>selector===(kind==='portal'?'[data-billing-portal]':'[data-checkout-plan]')?button:null}});
  return {assigned,requests,status:status.textContent};
 }finally{resetSession();Object.assign(globalThis,saved);}
}
test('approved live checkout response navigates to the hosted payment page',async()=>{
 const result=await paymentClick();assert.deepEqual(result.assigned,['https://checkout.stripe.com/c/pay/live']);
});

test('Stripe hosted checkout preserves its opaque fragment through the customer button',async()=>{
 const url='https://checkout.stripe.com/c/pay/cs_live_synthetic#fidkdWxOYHwnPyd1blpp';
 const result=await paymentClick({result:{url,sandbox:false}});
 assert.deepEqual(result.assigned,[url]);
});

test('billing navigation rejects oversized URLs and parser-normalized control characters',async()=>{
 for(const url of ['https://checkout.stripe.com/c/pay/x#'+'x'.repeat(4096),'https://checko\tut.stripe.com/c/pay/x']){
  const result=await paymentClick({result:{url,sandbox:false}});
  assert.equal(result.assigned.length,0);assert.ok(result.status);
 }
});
test('payment navigation rejects wrong mode, credentials, nonstandard port and unapproved hosts',async()=>{
 for(const response of [{url:'https://checkout.stripe.com/c/pay/live',sandbox:true},{url:'https://checkout.stripe.com:444/c/pay/live',sandbox:false},{url:'https://user@checkout.stripe.com/c/pay/live',sandbox:false},{url:'https://evil.example/pay',sandbox:false}]){
  const result=await paymentClick({result:response});assert.equal(result.assigned.length,0);assert.ok(result.status);
 }
});
test('portal management navigates only after the authenticated server returns its validated result',async()=>{
 const result=await paymentClick({kind:'portal',result:{url:'https://billing.stripe.com/p/session/verified',sandbox:false}});
 assert.deepEqual(result.requests,['/api/billing/portal']);assert.deepEqual(result.assigned,['https://billing.stripe.com/p/session/verified']);
});
test('live plan comparison presents production checkout and never claims an active subscriber has no subscription',()=>{
 const html=renderAccount(base);
 assert.ok(!html.includes('No subscription is active'));
 assert.ok(!html.includes('Publishing is not enabled yet'));
 assert.ok(!html.includes('<h3>Sandbox Billing</h3>'));
 assert.ok(html.includes('<h3>Billing</h3>'));assert.ok(html.includes('data-review-plan="starter"'));
});


test('scheduled and pending plan changes remain cancelable with explicit override disclosure',()=>{
 for(const status of ['scheduled','payment_pending','requested']){
 const html=renderAccount({...base,billing:{...base.billing,change:{plan:'starter',status,kind:'downgrade',sandbox:false}}});
 assert.ok(html.includes('data-cancel-subscription'));
 assert.ok(html.includes('overrides any remaining plan-change schedule'));
 assert.ok(html.includes('unused included allowance end now'));
 }
});

test('cancellation submission sends one structured acknowledgment with session CSRF protection',async()=>{
 const saved={document:globalThis.document,fetch:globalThis.fetch};const handlers={},requests=[],output={textContent:''},button={disabled:false};
 const form={reportValidity:()=>true,querySelector:()=>button};
 globalThis.document={querySelectorAll:()=>[],addEventListener:(name,fn)=>handlers[name]=fn,querySelector:selector=>selector==='[data-billing-management-status]'?output:null};
 globalThis.fetch=async(path,options)=>{requests.push({path,options});return {ok:true,status:200,json:async()=>path==='/api/account'?{...base,user:{...base.user,id:'owned-customer'},csrfToken:'owned-csrf'}:path==='/api/workspace'?{candidates:[],reviews:[],pipelineJobs:[]}:path==='/api/billing/cancel'?{status:'canceled'}:{}};};
 try{
  resetSession();await loadSession();requests.length=0;
  connectAccountControls({showWorkspace:()=>{},showAuth:()=>{},refresh:()=>{}});
  await handlers.submit({preventDefault(){},target:{closest:selector=>selector==='[data-cancel-subscription]'?form:null}});
  const sent=requests.filter(r=>r.path==='/api/billing/cancel');assert.equal(sent.length,1);
  assert.deepEqual(JSON.parse(sent[0].options.body),{acknowledged:true});
  assert.equal(sent[0].options.headers['X-CSRF-Token'],'owned-csrf');
 }finally{resetSession();Object.assign(globalThis,saved);}
});
