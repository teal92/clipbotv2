import test from 'node:test';
import assert from 'node:assert/strict';
import {passwordRequirements} from '../frontend/js/password-policy.js';
import {renderAuth} from '../frontend/js/views/auth.js';
test('password checks distinguish unmet requirements and common passwords',()=>{
 const weak=passwordRequirements('weak-password-123');
 assert.equal(weak.valid,false);assert.ok(weak.errors.some(error=>error.includes('uppercase')));
 assert.equal(passwordRequirements('Password123!').valid,false);
 assert.equal(passwordRequirements('StrongClipBot!2026').valid,true);
 assert.equal(passwordRequirements('A1!'+'x'.repeat(126)).valid,false);
});
test('signup renders checklist and login accepts legacy short credentials',()=>{
 const signup=renderAuth('signup',false),login=renderAuth('login',false);
 assert.ok(signup.includes('data-password-rules'));assert.ok(signup.includes('data-password-policy'));
 assert.ok(signup.includes('Username'));assert.ok(signup.includes('minlength="3"'));
 assert.ok(!login.includes('data-password-rules'));assert.ok(!login.includes('minlength="12"'));
});
import {bindPasswordPolicy} from '../frontend/js/password-policy.js';
test('delegated input updates strength and checklist after dynamic rendering, once',()=>{
 const handlers={},strength={textContent:''},meter={value:0};let registrations=0;
 const items=Array.from({length:6},(_,index)=>({dataset:{passwordRule:String(index)},passed:false,classList:{toggle(_name,value){items[index].passed=value;}},querySelector(){return this.check;},check:{textContent:''}}));
 const rules={dataset:{passwordRules:'late-password'},querySelector(selector){return selector.includes('strength')?strength:meter;},querySelectorAll(){return items;}};
 const root={addEventListener(type,handler){handlers[type]=handler;registrations++;},querySelectorAll(selector){return selector==='[data-password-rules]'?[rules]:[];}};
 bindPasswordPolicy(root);bindPasswordPolicy(root);
 assert.equal(registrations,3);
 const input={id:'late-password',value:'lowercaseonly1!',validity:'',matches:()=>true,setCustomValidity(message){this.validity=message;}};
 handlers.input({target:input});assert.ok(input.validity.includes('uppercase'));assert.equal(items[1].passed,false);
 input.value='StrongClipBot!2026';handlers.input({target:input});assert.equal(input.validity,'');assert.equal(meter.value,6);assert.ok(items.every(item=>item.passed));assert.ok(strength.textContent.includes('requirements met'));
 input.value='';handlers.input({target:input});assert.equal(meter.value,0);assert.ok(items.every(item=>!item.passed));
});
