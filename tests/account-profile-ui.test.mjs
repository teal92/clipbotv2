import test from 'node:test';
import assert from 'node:assert/strict';
import {renderAccount} from '../frontend/js/views/account.js';
const account={user:{name:'<script>',email:'a@test.com',username:'alice',avatar:'javascript:alert(1)'},plan:{name:'No active plan',coverage:null},billing:{message:'Billing not connected.'}};
test('account exposes accessible sections and protected profile fields',()=>{
 const html=renderAccount(account);for(const section of ['General','Plans &amp; Billing','Edit Profile'])assert.ok(html.includes(section));
 assert.ok(html.includes('data-profile-form'));assert.ok(html.includes('data-password-form'));
 assert.ok(html.includes('autocomplete="current-password"'));assert.ok(html.includes('autocomplete="new-password"'));
 assert.ok(!html.includes('<script>'));assert.ok(!html.includes('javascript:'));
 assert.ok(html.includes('Email changes require verification'));assert.ok(html.includes('data-account-panel="general"'));
});
import {connectAccountProfileControls} from '../frontend/js/controllers/account-profile-controller.js';
import {resetSession} from '../frontend/js/service-state.js';
test('a delayed avatar read cannot upload into a changed session',async()=>{
 const savedDocument=globalThis.document,savedReader=globalThis.FileReader,savedFetch=globalThis.fetch;
 let submit,reader,calls=0;
 globalThis.document={addEventListener:(type,handler)=>{if(type==='submit')submit=handler;}};
 globalThis.FileReader=class{constructor(){reader=this;}readAsDataURL(){}};
 globalThis.fetch=async()=>{calls++;throw Error('Unexpected upload');};
 const status={textContent:''},button={disabled:false},file={size:5,type:'image/png'};
 const form={hasAttribute:()=>false,querySelector:selector=>selector.includes('status')?status:selector.includes('submit')?button:{files:[file]}};
 try{connectAccountProfileControls({refresh:()=>{},showAuth:()=>{}});const pending=submit({target:{closest:()=>form},preventDefault:()=>{}});resetSession();reader.result='data:image/png;base64,YQ==';reader.onload();await pending;assert.equal(calls,0);assert.equal(button.disabled,false);}
 finally{globalThis.document=savedDocument;globalThis.FileReader=savedReader;globalThis.fetch=savedFetch;}
});
test('username is the sole display name and server change date is visible',()=>{
 const html=renderAccount({...account,user:{...account.user,name:'Legacy name',username:'current_name',usernameChangedAt:1700000000,usernameChangeAvailableAt:4102444800}});
 assert.ok(!html.includes('name="name"'));assert.ok(!html.includes('Display name<input'));
 assert.ok(html.includes('<h2>current_name</h2>'));assert.ok(html.includes('six calendar months'));
 assert.ok(html.includes('Next change available'));assert.ok(html.includes('readonly autocomplete="nickname"'));
});
test('profile new password has live requirements while current password accepts legacy values',()=>{
 const html=renderAccount(account);assert.ok(html.includes('data-password-rules="profile-new-password"'));
 assert.ok(html.includes('id="profile-new-password"'));assert.ok(html.includes('Password strength: not entered'));
 assert.ok(!html.match(/name="currentPassword"[^>]*minlength/));
});
