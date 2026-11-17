import test from 'node:test';
import assert from 'node:assert/strict';
import {renderAuth,renderSignupReadiness} from '../frontend/js/views/auth.js';

test('public entry presents the product and an actionable sign-in form',()=>{
 const html=renderAuth('login',false);
 assert.match(html,/Stay in the moment/);
 assert.match(html,/data-auth-form="login"/);
 assert.match(html,/autocomplete="current-password"/);
 assert.match(html,/href="\/reset-password.html"/);
 assert.match(html,/data-auth-mode="signup"/);
 assert.match(html,/DEMO DATA/);
 assert.match(html,/\/showcase\/demo.html#scouting/);
 assert.doesNotMatch(html,/Design preview only|data-dev-bypass/);
});
test('signup retains policy consent, username and password checks on the landing',()=>{
 const html=renderAuth('signup',false);
 assert.match(html,/Stay in the moment/);
 assert.match(html,/data-auth-form="signup"/);
 assert.match(html,/name="name"[^>]*required/);
 assert.match(html,/name="termsVersion" value="2026-10-15.2" required/);
 assert.match(html,/autocomplete="new-password"/);
 assert.match(html,/minlength="12"/);
 assert.match(html,/data-auth-mode="login"/);
 assert.equal((html.match(/<form /g)||[]).length,1);
});
test('email verification remains a distinct readiness screen',()=>{
 const html=renderSignupReadiness({});
 assert.match(html,/data-signup-check/);
 assert.doesNotMatch(html,/clipbot-landing|data-auth-form/);
});
test('public tour offers scouts and dashboard without the sample Clips review',()=>{
 const html=renderAuth('login',false);
 assert.match(html,/data-tour="scouting"/);
 assert.match(html,/data-tour="dashboard"/);
 assert.doesNotMatch(html,/data-tour="clips"|demo.html#clips|Try a sample review/);
});
