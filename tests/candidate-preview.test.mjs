import test from 'node:test';
import assert from 'node:assert/strict';
import {renderClips} from '../frontend/js/views/clips.js';
import {renderClipPreview} from '../frontend/js/controllers/clip-preview-controller.js';
test('candidate preview opens only validated loopback media without approval',()=>{
 const candidate={id:'id',creator:'creator',platform:'twitch',duration:'38s',previewFormat:'blurred_fit',previewUrl:'http://127.0.0.1:8767/preview/'+'a'.repeat(64)};
 const state={candidates:[candidate],reviews:[]},queue=renderClips(state),html=renderClipPreview('candidate','id',state);
 assert.match(queue,/data-clip-preview="id"/);assert.doesNotMatch(queue,/<video/);
 assert.match(html,/<video/);assert.match(html,/\/media\//);assert.doesNotMatch(html,/target="_blank"/);assert.match(html,/data-clip-action="approve"/);assert.doesNotMatch(html,/data-clip-action="preview" disabled/);
 const bad=renderClips({candidates:[{...candidate,previewUrl:'https://evil.test/private'}],reviews:[]});assert.doesNotMatch(bad,/href="https:\/\/evil/);assert.match(bad,/being prepared/);
});
