import test from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import vm from 'node:vm';
import {renderCustomerReadiness} from '../frontend/js/customer-access.js';

test('readiness shows available verification and requires explicit policy checkbox',()=>{
 const html=renderCustomerReadiness({emailVerified:false,policyAccepted:false,emailDeliveryAvailable:true,policyVersion:'current'});
 assert.ok(html.includes('data-request-verification'));
 assert.ok(html.includes('name="acknowledged" required'));
 assert.ok(html.includes('/terms')&&html.includes('/privacy')&&html.includes('/acceptable-use'));
 assert.ok(!html.includes('data-request-verification disabled'));
});

test('unconfigured email cannot be requested and policy version escapes markup',()=>{
 const html=renderCustomerReadiness({emailVerified:false,policyAccepted:false,emailDeliveryAvailable:false,policyVersion:'"><script>alert(1)</script>'});
 assert.ok(html.includes('data-request-verification disabled'));
 assert.ok(!html.includes('<script>'));
 assert.equal(renderCustomerReadiness(undefined),'');
});

test('verified accepted account offers neither repeated verification nor stale acceptance',()=>{
 const html=renderCustomerReadiness({emailVerified:true,policyAccepted:true,emailDeliveryAvailable:true,policyVersion:'current'});
 assert.ok(html.includes('Email: Verified')&&html.includes('Current policies: Accepted'));
 assert.ok(!html.includes('data-request-verification')&&!html.includes('data-accept-policy'));
});

async function verificationPage({signedIn=true}={}){
 const source=await readFile(new URL('../frontend/js/email-verification.js',import.meta.url),'utf8');
 const token='A'.repeat(43),button={disabled:false},output={textContent:''};let handler,cleaned,calls=[];
 const form={hidden:false,querySelector:()=>button,addEventListener:(type,fn)=>{handler=fn;}};
 const context={URLSearchParams,Error,JSON,window:{location:{hash:'#token='+token,pathname:'/verify-email.html'},history:{replaceState:(_state,_title,path)=>{cleaned=path;}}},document:{querySelector:selector=>selector==='[data-email-verification]'?form:output},fetch:async(path,options)=>{calls.push({path,options});if(path==='/api/account')return {status:signedIn?200:401,ok:signedIn,json:async()=>({csrfToken:'synthetic-csrf'})};return {status:200,ok:true,json:async()=>({emailVerified:true})};}};
 vm.runInNewContext(source,context);
 assert.equal(cleaned,'/verify-email.html');
 await handler({preventDefault:()=>{}});
 return {calls,output,form,button,token};
}

test('verification posts token only to CSRF-protected same-origin endpoint',async()=>{
 const result=await verificationPage();
 assert.equal(result.calls.length,2);
 const request=result.calls[1];assert.equal(request.path,'/api/account/verify-email');
 assert.equal(request.options.headers['X-CSRF-Token'],'synthetic-csrf');
 assert.equal(JSON.parse(request.options.body).token,result.token);
 assert.equal(request.options.credentials,'same-origin');
 assert.ok(result.form.hidden&&result.output.textContent.startsWith('Email verified.'));
});

test('signed-out verification never submits a token and retains useful sign-in instructions',async()=>{
 const result=await verificationPage({signedIn:false});
 assert.equal(result.calls.length,1);assert.ok(result.output.textContent.includes('Sign in to the account'));
 assert.equal(result.button.disabled,false);
});
