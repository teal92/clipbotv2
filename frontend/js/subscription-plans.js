import {readStored,writeStored} from './ui-utils.js';
// Proposed entitlements only. Server authentication, billing and atomic budgets are still required.
export const PLANS=Object.freeze([
 Object.freeze({id:'starter',name:'Starter',monthlyPrice:7,sources:6,streamerFavorites:0,categoryFavorites:0,dailyReviews:15,monthlyReviews:450,uniqueClipsDaily:20,aiCostCeilingUSD:2,description:'A practical starting point for daily posting.'}),
 Object.freeze({id:'creator',name:'Creator',monthlyPrice:25,sources:12,streamerFavorites:3,categoryFavorites:3,dailyReviews:45,monthlyReviews:1350,uniqueClipsDaily:20,aiCostCeilingUSD:6,description:'More scouts and priority creators and categories.'}),
 Object.freeze({id:'pro',name:'Pro',monthlyPrice:60,sources:30,streamerFavorites:10,categoryFavorites:10,dailyReviews:120,monthlyReviews:3600,uniqueClipsDaily:null,aiCostCeilingUSD:8,description:'120 reviews per day and 3,600 per month.'}),
 Object.freeze({id:'custom',name:'Custom',monthlyPrice:null,sources:null,streamerFavorites:null,categoryFavorites:null,dailyReviews:null,monthlyReviews:null,aiCostCeilingUSD:null,description:'Scale your reviews, scouts and favorites. Request a quote.'}),
]);
const KEY='clipbot-plan-interest-v1',CUSTOM_KEY='clipbot-custom-plan-v1';
export const CUSTOM_LIMITS=Object.freeze({
 scouts:Object.freeze({min:0,max:40,label:'Total scouts'}),
 streamerFavorites:Object.freeze({min:0,max:25,label:'Favorite streamers'}),
 categoryFavorites:Object.freeze({min:0,max:25,label:'Favorite categories'}),
 dailyReviews:Object.freeze({min:12,max:180,label:'Candidate reviews per day'}),
});
export const DEFAULT_CUSTOM=Object.freeze({scouts:6,streamerFavorites:0,categoryFavorites:0,dailyReviews:12});
export function getPlanInterest(storage){const saved=readStored(KEY,'',storage);return PLANS.some(plan=>plan.id===saved)?saved:'';}
export function savePlanInterest(id,storage){return PLANS.some(plan=>plan.id===id)?writeStored(KEY,id,storage):{ok:false,error:'Choose one of the proposed plans.'};}
function validateCustom(input){
 const value={};
 for(const [key,{min,max}] of Object.entries(CUSTOM_LIMITS)){
  if(!Number.isInteger(input?.[key])||input[key]<min||input[key]>max)return null;
  value[key]=input[key];
 }
 return value;
}
// This is a proposal price, not a trusted billing entitlement. Recompute on the server.
export function calculateCustomPrice(input){
 const value=validateCustom(input);if(!value)return null;
 // Calculate currency in whole cents so exact boundaries never receive a rounding surcharge.
 const rawCents=700+Math.max(0,value.scouts-6)*50+value.streamerFavorites*20+value.categoryFavorites*20+Math.max(0,value.dailyReviews-12)*45;
 const monthlyReviews=value.dailyReviews*30;
 const estimatedAICost=Math.round(monthlyReviews*0.0013*100)/100;
 return {rawPrice:rawCents/100,monthlyPrice:Math.min(85,Math.max(10,Math.ceil(rawCents/500)*5)),monthlyReviews,estimatedAICost,stressAICost:Math.round(monthlyReviews*0.002*100)/100,aiSpendCeiling:Math.min(12,Math.max(2,Math.ceil(monthlyReviews*12/5400)))};
}
export function getCustomPlan(storage){return validateCustom(readStored(CUSTOM_KEY,DEFAULT_CUSTOM,storage))??{...DEFAULT_CUSTOM};}
export function saveCustomPlan(input,storage){const value=validateCustom(input);return value?writeStored(CUSTOM_KEY,value,storage):{ok:false,error:'Choose whole numbers within the four slider ranges. Custom drafts do not activate billing.'};}
// Illustrative Haiku 5.5 cost: 20k input + 2k output tokens TOTAL per review, no tools.
export function estimateReviewCost(reviews){if(!Number.isInteger(reviews)||reviews<0||reviews>10000)return null;return Math.round(reviews*0.003*100)/100;}


export function postingAllowanceText(limit){return limit===null?'No ClipBot posting cap; platform rules apply':`${limit} unique clips/day`;}
