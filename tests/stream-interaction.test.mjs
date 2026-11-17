import test from 'node:test';
import assert from 'node:assert/strict';
import * as activity from '../frontend/js/views/stream-interaction.js';
test('real numeric channels render individually; missing and stale channels stay explicit',()=>{
 const now=1000, row={at:995,audioDb:-30,chatMessages:2,cues:['speech_phrase']};
 const html=activity.renderStreamInteraction({state:'monitoring',interaction:{samples:[{...row,at:990},row]}},now);
 assert.match(html,/Audio/);assert.match(html,/Chat/);assert.match(html,/speech phrase/);assert.match(html,/polyline/);
 assert.match(activity.renderStreamInteraction({interaction:{samples:[{...row,audioDb:null,chatMessages:null}]}},now),/unavailable/);
 assert.match(activity.renderStreamInteraction({interaction:{samples:[row]}},1200),/stale/);
 assert.doesNotMatch(activity.renderStreamInteraction({},now),/polyline/);
});
test('bounded samples reject coerced numeric strings and do not bridge missing observations',()=>{
 const points=activity.interactionSamples({samples:[{at:990,audioDb:'-20',chatMessages:null,cues:[]},{at:995,audioDb:-25,chatMessages:0,cues:[]}]},1000);
 assert.equal(points[0].audioDb,null);assert.equal(points[1].chatMessages,0);
 assert.equal(activity.interactionSamples({samples:Array.from({length:40},(_,n)=>({at:900+n,audioDb:-20,chatMessages:0,cues:[]}))},1000).length,24);
});

test('unavailable or disconnected chat labels retained readings as historical immediately',()=>{
 const interaction={samples:[{at:995,audioDb:-30,chatMessages:0,cues:[]}]};
 for(const chatStatus of ['unavailable','disabled','connecting']){
  const html=activity.renderStreamInteraction({state:'monitoring',chatStatus,interaction},1000);
  assert.match(html,/Chat<\/span><small>unavailable/);
  assert.match(html,/last: 0 messages \/ 5s/);
 }
 const html=activity.renderStreamInteraction({state:'monitoring',chatStatus:'connected',interaction},1000);
 assert.match(html,/Chat<\/span><small>0 messages \/ 5s/);
});
