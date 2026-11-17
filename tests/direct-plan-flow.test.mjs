import test from 'node:test';
import assert from 'node:assert/strict';
import {renderAccount} from '../frontend/js/views/account.js';
const account={user:{name:'Customer',email:'customer@example.com'},plan:{name:'Creator',coverage:null},billing:{mode:'live',connected:true,customAvailable:true,subscription:{plan:'creator',status:'active',expires:Date.now()/1000+86400}}};
test('plan cards are direct review actions with always-open plan capacity sections',()=>{
 const html=renderAccount(account);
 assert.match(html,/data-review-plan="starter"/);assert.match(html,/data-open-custom-builder/);
 assert.match(html,/<dialog[^>]*data-custom-builder-dialog/);
 assert.match(html,/data-plan-limits="starter"/);assert.match(html,/data-plan-limits="custom"/);
 assert.doesNotMatch(html,/Patreon|Review Selected Plan|<h3>Subscribe<|data-account-dialog-open="plans"|data-account-tab="settings"/);
 assert.doesNotMatch(html,/<details[^>]*><summary>Included Usage/);
});
