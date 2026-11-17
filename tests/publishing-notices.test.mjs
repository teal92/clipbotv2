import test from 'node:test';
import assert from 'node:assert/strict';
import {renderPublishing} from '../frontend/js/views/publishing.js';
test('publishing keeps complete per-platform delivery and diagnostics visible',()=>{
 const clip={id:'a'.repeat(32),title:'Clip',caption:'Caption',artifact:{duration:20}};
 const state={ready:[clip],publications:[{id:'b'.repeat(32),clipId:clip.id,platform:'instagram',status:'published',receipt:{verifiedAt:1}},{id:'c'.repeat(32),clipId:clip.id,platform:'facebook',status:'published',receipt:{verifiedAt:1}},{id:'d'.repeat(32),clipId:clip.id,platform:'tiktok',status:'unknown'}]};
 const html=renderPublishing(undefined,state,{platforms:[]});
 assert.match(html,/Instagram: Published/);assert.match(html,/Facebook: Published/);
 assert.match(html,/TikTok: Awaiting confirmation/);
 assert.match(html,/Download logs bundle/);assert.doesNotMatch(html,/<h3>Publishing logs/);
});
