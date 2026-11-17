import test from 'node:test';
import assert from 'node:assert/strict';
import {parseBulkPhrases,handleTriggerClick} from '../frontend/js/controllers/trigger-controller.js';
import {renderTriggerControls} from '../frontend/js/views/trigger-controls.js';

test('bulk phrases split commas into trimmed independent rules with manual dropdown defaults',()=>{
 assert.deepEqual(parseBulkPhrases(' no way, great play, clip that '),[
  {phrase:'no way',source:'speech',priority:'medium'},
  {phrase:'great play',source:'speech',priority:'medium'},
  {phrase:'clip that',source:'speech',priority:'medium'}]);
});
test('bulk phrases skip empty entries and existing duplicates without changing existing settings',()=>{
 const existing=[{phrase:'NO WAY',source:'either',priority:'high'}];
 assert.deepEqual(parseBulkPhrases('no way,, great play, GREAT PLAY,',existing),[{phrase:'great play',source:'speech',priority:'medium'}]);
 assert.equal(existing[0].source,'either');
});
test('bulk import rejects overflow and invalid phrases atomically',()=>{
 const existing=Array.from({length:19},(_,i)=>({phrase:`rule ${i}`}));
 assert.throws(()=>parseBulkPhrases('new one, new two',existing),/20/);
 for(const text of ['', 'x'.repeat(81), 'okay,bad\nphrase','x'.repeat(2001)])assert.throws(()=>parseBulkPhrases(text));
 assert.equal(existing.length,19);
});
test('bulk control is beside add phrase and has a separate update action',()=>{
 const html=renderTriggerControls();
 assert.match(html,/data-trigger-add>Add phrase<\/button><button[^>]*data-trigger-bulk-open[^>]*>Bulk phrases/);
 assert.match(html,/data-trigger-bulk-update>Update/);
});
test('bulk Update appends escaped phrase rows and preserves unrelated controls',()=>{
 let appended='',status={textContent:''},input={value:'<img src=x onerror=alert(1)>, nice play'},panel={hidden:false};
 const form={querySelectorAll:()=>[],querySelector(selector){return ({'[data-trigger-status]':status,'[data-trigger-bulk-input]':input,'[data-trigger-bulk]':panel,'[data-trigger-rules]':{insertAdjacentHTML(position,html){appended+=html;}}})[selector];}};
 const button={closest:()=>form,matches:selector=>selector==='[data-trigger-bulk-update]'};
 assert.equal(handleTriggerClick({target:{closest:()=>button}}),true);
 assert.equal((appended.match(/data-trigger-rule /g)||[]).length,2);
 assert.ok(!appended.includes('<img'));
 assert.match(appended,/&lt;img/);
 assert.match(status.textContent,/2 phrases/);
 assert.equal(input.value,'');
});
