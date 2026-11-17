import test from 'node:test';
import assert from 'node:assert/strict';
import {validatedCustomQuote} from '../frontend/js/controllers/custom-billing-controller.js';
const custom={scouts:12,streamerFavorites:3,categoryFavorites:3,dailyReviews:45};
const quote={plan:'custom',currency:'USD',monthlyCents:3000,monthlyReviews:1350,quantities:custom};
test('Custom confirmation accepts only exact server capacities and supported price buckets',()=>{
 assert.equal(validatedCustomQuote(quote,custom).monthlyCents,3000);
 for(const bad of [{...quote,monthlyCents:1},{...quote,monthlyCents:3050},{...quote,currency:'EUR'},{...quote,plan:'pro'},{...quote,quantities:{...custom,scouts:40}}])assert.throws(()=>validatedCustomQuote(bad,custom));
});
