import { readStored, writeStored } from '../ui-utils.js';
const KEY='clipbot-learning-v1';
const EMPTY={preferences:{contentFocus:'',avoidTopics:''},reviews:[]};
function preferences(value) {
 return value && ['contentFocus','avoidTopics'].every(key=>typeof value[key]==='string'&&value[key].length<=500)
 ? {contentFocus:value.contentFocus.trim(),avoidTopics:value.avoidTopics.trim()}:null;
}
function review(event) {
 const candidate=event?.candidate;
 const feedback=event?.user_feedback;
 if (!candidate || typeof candidate.id!=='string'||!candidate.id||candidate.id.length>150||!['approve','reject'].includes(feedback?.decision)) return null;
 const text=value=>typeof value==='string'?value.slice(0,1000):'';
 return {candidate:{id:candidate.id,creator:text(candidate.creator),platform:text(candidate.platform),duration:text(candidate.duration),category:text(candidate.category)},user_feedback:{decision:feedback.decision,reasons:Array.isArray(feedback.reasons)?feedback.reasons.filter(x=>typeof x==='string').slice(0,10).map(text):[],justification:text(feedback.justification)},created_at:Number.isFinite(Date.parse(event.created_at))?new Date(event.created_at).toISOString():new Date().toISOString(),syncStatus:'local'};
}
export function getLearning(storage) {
 const data=readStored(KEY,EMPTY,storage);
 return {preferences:preferences(data?.preferences)??{...EMPTY.preferences},reviews:Array.isArray(data?.reviews)?data.reviews.slice(-200).map(review).filter(Boolean):[]};
}
export function savePreferences(input,storage) {
 const value=preferences(input);
 return value ? writeStored(KEY,{...getLearning(storage),preferences:value},storage):{ok:false,error:'Keep each preference field to 500 characters or fewer.'};
}
export function recordReview(event,storage) {
 const value=review(event);
 if(!value) return {ok:false,error:'The review is invalid.'};
 const state=getLearning(storage);
 state.reviews=[...state.reviews.filter(item=>item.candidate.id!==value.candidate.id),value].slice(-200);
 return writeStored(KEY,state,storage);
}
