import {renderPlanOptions} from '../frontend/js/views/plan-options.js';
import test from 'node:test';
import assert from 'node:assert/strict';
import {renderPlanChange} from '../frontend/js/views/billing-changes.js';
test('active customers choose cards without a second plan selector',()=>{
 const billing={mode:'live',connected:true,subscription:{plan:'starter',status:'active',expires:Date.now()/1000+3600}};
 const html=renderPlanOptions(null,billing);
 assert.match(html,/data-review-plan="creator"/);assert.match(html,/data-review-plan="pro"/);
 assert.doesNotMatch(renderPlanChange(billing),/data-plan-change-form/);
});

test('pending payment provides only a verified Stripe invoice link and prevents competing changes',()=>{
 const html=renderPlanChange({mode:'live',connected:true,subscription:{plan:'starter',status:'active',expires:Date.now()/1000+3600},change:{plan:'creator',status:'payment_pending',paymentUrl:'https://invoice.stripe.com/i/test'}});
 assert.ok(html.includes('Payment pending'));assert.ok(html.includes('Complete payment'));assert.ok(!html.includes('data-plan-change-form'));
 const unsafe=renderPlanChange({change:{status:'payment_pending',paymentUrl:'https://evil.example/steal'}});
 assert.ok(!unsafe.includes('href="https://evil.example'));
});
test('scheduled downgrade has a date and expired subscription cannot change plans',()=>{
 const html=renderPlanChange({change:{plan:'starter',status:'scheduled',effectiveAt:Date.UTC(2026,10,13)/1000}});
 assert.ok(html.includes('Lower limits active; renewal price scheduled'));assert.ok(html.includes('UTC'));assert.ok(!html.includes('data-plan-change-form'));
 assert.ok(!renderPlanChange({mode:'live',connected:true,subscription:{plan:'starter',status:'active',expires:0}}).includes('data-plan-change-form'));
});
test('uncertain request offers a same-target explicit retry without another plan selector',()=>{
 const html=renderPlanChange({mode:'live',connected:true,subscription:{plan:'starter',status:'active',expires:Date.now()/1000+3600},change:{plan:'creator',status:'requested'}});
 assert.ok(html.includes('data-retry-plan-change="creator"'));assert.ok(html.includes('Retry Plan Change'));
 assert.ok(!html.includes('data-plan-change-form'));
});
test('Custom capacity is chosen in a popup for both standard and Custom subscribers',()=>{
 for(const plan of ['starter','custom']){
  const html=renderPlanOptions(null,{mode:'live',connected:true,customAvailable:true,subscription:{plan,status:'active',expires:Date.now()/1000+3600}});
  assert.match(html,/data-open-custom-builder/);assert.match(html,/data-custom-builder-dialog/);assert.match(html,/data-custom-subscribe/);
 }
});
