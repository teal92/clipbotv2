import test from 'node:test';
import assert from 'node:assert/strict';
import {renderAccount} from '../frontend/js/views/account.js';
import {renderSettings} from '../frontend/js/views/settings.js';
const account={user:{name:'Customer',email:'user@example.com',username:'customer'},plan:{name:'Creator',coverage:null},billing:{mode:'live',connected:true,message:'Stripe live billing is connected.',subscription:{plan:'creator',status:'active',expires:Date.now()/1000+86400}}};
test('Billing leads into plans and change control opens a native dialog',()=>{
 const html=renderAccount(account,{settingsHtml:renderSettings()});
 assert.match(html,/data-review-plan="starter"/);
 assert.match(html,/<dialog[^>]*data-custom-builder-dialog/);
 assert.ok(html.indexOf('<h3>Billing')<html.indexOf('plan-grid'));assert.doesNotMatch(html,/Change ClipBot subscription plan/);
 assert.match(html,/Recommended/);assert.doesNotMatch(html,/Most popular/);
});
test('production account copy does not offer sandbox checkout or fake coverage',()=>{
 const html=renderAccount(account,{settingsHtml:renderSettings()});
 assert.doesNotMatch(html,/Sandbox Billing|Save Plan Preference|Choose .* for discussion|during beta|Sandbox only|Confirm Test/);
 const off=renderAccount({...account,billing:{mode:'test',connected:true}},{});
 assert.doesNotMatch(off,/data-checkout-plan="starter"(?![^>]*disabled)/);
});
test('security guidance is alongside password entry rather than a settings card',()=>{
 const html=renderAccount(account,{settingsHtml:renderSettings()});
 assert.doesNotMatch(renderSettings(),/<h3>Security<\/h3>/);
 assert.match(html,/data-password-security/);assert.match(html,/<dialog[^>]*data-account-dialog="security"/);
 assert.match(html,/password hashes/);assert.match(html,/data-password-form/);
});
