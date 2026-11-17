import test from 'node:test';
import assert from 'node:assert/strict';
import {onboardingStep,renderOnboarding,SETUP_GUIDE} from '../frontend/js/onboarding.js';
import {renderCompanionStatus} from '../frontend/js/views/companion.js';
const paid={plan:{active:true,coverage:{scouts:6}},billing:{mode:'live',subscription:{status:'active',expires:Date.now()/1000+86400}}};
const ready={state:'ready',companionVersion:'0.2.7',requiredVersion:'0.2.7'};
const connected={platforms:[{id:'kick',connected:true,status:'connected',monitoringReady:true}]};
test('first launch requires a genuine worker before accounts and paid coverage',()=>{
 assert.equal(onboardingStep({}, {state:'offline'},connected),'companion');
 assert.equal(onboardingStep({},ready,{platforms:[]}), 'connections');
 assert.equal(onboardingStep({},ready,connected),'plan');
 assert.equal(onboardingStep(paid,ready,connected),'ready');
});
test('expired, wrong-mode and mere plan preferences never authorize Start',()=>{
 for(const account of [{plan:{active:false}}, {...paid,billing:{mode:'test',subscription:paid.billing.subscription}}, {...paid,billing:{mode:'live',subscription:{status:'active',expires:1}}}])assert.equal(onboardingStep(account,ready,connected),'plan');
 assert.equal(onboardingStep(paid,{...ready,companionVersion:'old'},connected),'companion');
 assert.equal(onboardingStep(paid,ready,{platforms:[{id:'kick',connected:true,status:'permissions_missing'}]}),'connections');
});
test('guide is before Start, opens a safe new tab and does not simulate installation',()=>{
 const html=renderCompanionStatus({state:'offline'});
 assert.ok(html.indexOf('Click Here for initial ClipBot setup')<html.indexOf('Start ClipBot'));
 assert.ok(html.includes(`href="${SETUP_GUIDE}"`));assert.match(html,/target="_blank" rel="noopener noreferrer"/);
 assert.match(renderOnboarding('companion'),/connected companion/);
 assert.match(renderOnboarding('plan'),/confirmed payment/);
});

test('required email and policy verification precede installation and checkout',()=>{assert.equal(onboardingStep({...paid,readiness:{enforced:true,ready:false}},ready,connected),'account');assert.match(renderOnboarding('account'),/Verify your email/);});

test('complimentary owner showcase replaces only the paid-plan setup step',()=>{
 const owner={isAdmin:true,plan:{active:true,coverage:{ownerShowcase:true,scouts:40}},readiness:{enforced:true,ready:true,policyAccepted:true},billing:{mode:'live',subscription:null}};
 assert.equal(onboardingStep(owner,ready,connected),'ready');
 assert.equal(onboardingStep({...owner,isAdmin:false},ready,connected),'plan');
 assert.equal(onboardingStep({...owner,plan:{active:true,coverage:{ownerShowcase:'true'}}},ready,connected),'plan');
 assert.equal(onboardingStep({...owner,readiness:{...owner.readiness,ready:false}},ready,connected),'account');
 assert.equal(onboardingStep(owner,{state:'offline'},connected),'companion');
 assert.equal(onboardingStep(owner,ready,{platforms:[]}),'connections');
});
