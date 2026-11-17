import test from 'node:test';
import assert from 'node:assert/strict';
import {renderUsage} from '../frontend/js/views/usage.js';
const usage={inputTokens:300,outputTokens:50,spentMicros:1000,reservedMicros:500,reviewsToday:1,reviewsMonth:450,reviewLimit:15,monthlyReviewLimit:450,spendLimitMicros:2000000,activity:[{day:'2026-10-30',tokens:100},{day:'2026-11-29',tokens:250}],aiEnabled:true,throttled:false,billingPeriod:{start:Date.UTC(2026,9,30,12)/1000,end:Date.UTC(2026,10,30,12)/1000},periodReconciliationRequired:false};
test('usage labels paid quotas and displays activity across the complete billing cycle',()=>{
 const html=renderUsage(usage);assert.ok(html.includes('Reviews this billing period'));assert.ok(html.includes('Billing period'));assert.ok(html.includes('Monthly candidate reviews'));
 assert.ok(html.includes('2026-10-30: 100 tokens'));assert.ok(html.includes('2026-11-29: 250 tokens'));
 assert.ok(!html.includes('Daily and monthly resets use UTC'));assert.ok(html.includes('Daily limits reset in UTC'));
});
test('unreconciled paid period explicitly pauses usage',()=>{
 const html=renderUsage({...usage,billingPeriod:null,periodReconciliationRequired:true,aiEnabled:false});
 assert.ok(html.includes('Billing period awaiting reconciliation'));assert.ok(html.includes('paid AI reviews are paused'));
});
