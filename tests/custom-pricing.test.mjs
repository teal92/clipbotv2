import test from 'node:test';
import assert from 'node:assert/strict';
import {calculateCustomPrice,CUSTOM_LIMITS,saveCustomPlan,getCustomPlan} from '../frontend/js/subscription-plans.js';
import {renderPlanOptions} from '../frontend/js/views/plan-options.js';
const baseline={scouts:6,streamerFavorites:0,categoryFavorites:0,dailyReviews:12};
const maxed={scouts:40,streamerFavorites:25,categoryFavorites:25,dailyReviews:180};
const storage=()=>{const data=new Map();return {getItem:key=>data.get(key)??null,setItem:(key,value)=>data.set(key,value)};};
test('four bounded sliders replace custom numeric inputs',()=>{
 const html=renderPlanOptions('custom');
 assert.equal((html.match(/type="range"/g)||[]).length,4);assert.ok(!html.includes('type="number"'));
 assert.ok(html.includes('crashes'));assert.ok(html.includes('platform/account'));assert.ok(html.includes('data-custom-price'));
});
test('maximum combination prices at $85 with transparent cost assumptions',()=>{
 const result=calculateCustomPrice(maxed);
 assert.equal(result.monthlyPrice,85);assert.equal(result.monthlyReviews,5400);
 assert.equal(result.estimatedAICost,7.02);assert.equal(result.stressAICost,10.8);assert.equal(result.aiSpendCeiling,12);
});
test('each slider contributes to pricing without exceeding allowed boundaries',()=>{
 const initial=calculateCustomPrice(baseline);
 for(const field of Object.keys(CUSTOM_LIMITS)){
  const changed={...baseline,[field]:CUSTOM_LIMITS[field].max};
  assert.ok(calculateCustomPrice(changed).rawPrice>initial.rawPrice);
  assert.equal(saveCustomPlan({...baseline,[field]:CUSTOM_LIMITS[field].max+1},storage()).ok,false);
  assert.equal(saveCustomPlan({...baseline,[field]:CUSTOM_LIMITS[field].min-1},storage()).ok,false);
 }
 const zero={...baseline,scouts:0,streamerFavorites:25,categoryFavorites:25};
 assert.equal(saveCustomPlan(zero,storage()).ok,true);
 assert.equal(calculateCustomPrice({...baseline,dailyReviews:12.5}),null);
});
test('drafts retain all four values and recover safely from old formats',()=>{
 const store=storage();assert.equal(saveCustomPlan(maxed,store).ok,true);assert.deepEqual(getCustomPlan(store),maxed);
 store.setItem('clipbot-custom-plan-v1',JSON.stringify({aiReviews:3000,scouts:36,streamerFavorites:12,categoryFavorites:12}));
 assert.equal(getCustomPlan(store).dailyReviews,12);assert.equal(getCustomPlan(store).scouts,6);
});

test('exact five-dollar boundaries do not gain an accidental surcharge',()=>{
 const config={scouts:0,streamerFavorites:1,categoryFavorites:0,dailyReviews:96};
 const quote=calculateCustomPrice(config);assert.equal(quote.rawPrice,45);assert.equal(quote.monthlyPrice,45);
});

test('plan cards describe unique clips and unrestricted Custom posting',()=>{
 const html=renderPlanOptions('starter');
 assert.ok(html.includes('20 unique clips/day'));
 assert.ok(html.includes('Failed uploads and retries'));
 assert.ok(html.includes('No ClipBot posting cap'));
 assert.ok(!html.includes('posts per platform per day'));
});
