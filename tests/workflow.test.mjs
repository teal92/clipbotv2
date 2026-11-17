import test from 'node:test';
import assert from 'node:assert/strict';
import {clipWorkflowCounts} from '../frontend/js/views/workflow.js';
import {renderProcessing} from '../frontend/js/views/processing.js';
import {renderPublishing} from '../frontend/js/views/publishing.js';
test('clip counters distinguish recordings, processing, review and normal rejection',()=>{
 assert.deepEqual(clipWorkflowCounts(['capturing','transcribing','analyzing','review','rendering','ready','failed'].map(stage=>({stage}))),{collected:5,processing:3,review:1});
 assert.equal(clipWorkflowCounts([{stage:'failed',errorCode:'not_selected'}]).collected,1);
});
test('processing keeps old failures outside the active stage workflow',()=>{
 const jobs=Array.from({length:100},(_,i)=>({id:String(i),source:{platform:'kick',login:'old'+i},stage:'failed',metrics:{cpuPercent:20}}));
 jobs.push({id:'new',source:{platform:'twitch',login:'active'},stage:'transcribing',updated:1});
 const html=renderProcessing({workerConnected:true,pipelineJobs:jobs});
 const active=html.split('<h3>Processing queue</h3>')[1].split('<details')[0];
 assert.match(active,/active/);assert.doesNotMatch(active,/old99/);assert.match(html,/Recent failures and stopped jobs \(100\)/);assert.match(html,/queue-stage-scroll/);
});
test('publishing uses provider confirmation stages and preserves posting approval',()=>{
 const html=renderPublishing({platform:'facebook',caption:''},{workerConnected:true,ready:[{id:'a',title:'clip',previewUrl:'http://127.0.0.1:8767/preview/'+'a'.repeat(64)}],publications:[{id:'attempt',clipId:'a',platform:'facebook',status:'uploading'}]});
 assert.match(html,/Ready to post/);assert.match(html,/Uploading/);assert.match(html,/data-publish-platform/);assert.match(html,/permission to publish/);assert.match(html,/data-pipeline-reconcile/);
});

test('active local edits remain visible as processing',()=>{
 assert.deepEqual(clipWorkflowCounts([{stage:'editing'}]),{collected:1,processing:1,review:0});
 assert.match(renderProcessing({pipelineJobs:[{id:'edit',source:{login:'editingcreator'},stage:'editing'}]}),/editingcreator/);
});
