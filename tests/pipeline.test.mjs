import test from 'node:test';
import assert from 'node:assert/strict';
import {safePreviewUrl} from '../frontend/js/controllers/pipeline-controller.js';
import {renderPublishing} from '../frontend/js/views/publishing.js';
test('preview links accept only scoped local worker capabilities',()=>{
 const url='http://127.0.0.1:8767/preview/'+'a'.repeat(64);assert.equal(safePreviewUrl(url),url);
 for(const bad of ['javascript:alert(1)','http://evil.test/video','http://127.0.0.1:8767/preview/../../secret','http://user:pass@127.0.0.1:8767/preview/'+'a'.repeat(64)])assert.throws(()=>safePreviewUrl(bad));
});
test('publishing presents read-only approved clips and explicit permission notice',()=>{
 const state={ready:[{id:'a'.repeat(32),title:'<img>',caption:'a caption',previewUrl:'http://127.0.0.1:8767/preview/'+'b'.repeat(64)}],published:[],publications:[]};
 const html=renderPublishing(undefined,state);
 assert.match(html,/data-publish-platform/);assert.match(html,/permission to publish/);assert.ok(!html.includes('<img>'));
 assert.match(html,/Choose visibility/);
});

