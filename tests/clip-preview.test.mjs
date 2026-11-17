import test from 'node:test';
import assert from 'node:assert/strict';
import {renderClips} from '../frontend/js/views/clips.js';
import {renderPublishing} from '../frontend/js/views/publishing.js';
const candidate={id:'one',creator:'Creator',title:'Title',platform:'twitch',category:'Game',duration:'38s',score:88,previewFormat:'blurred_fit',previewUrl:'http://127.0.0.1:8767/preview/'+'a'.repeat(64)};
const review={candidate:{id:'one',creator:'Creator'},user_feedback:{decision:'reject',reasons:['Needs context'],justification:'Saved note'},localFeedbackStatus:'confirmed'};
test('Clips leaves rendering and publishing to their own pages',()=>{
 const html=renderClips({candidates:[candidate],ready:[candidate],processing:[{stage:'rendering'}]});
 assert.doesNotMatch(html,/<h3>Editing|<h3>Ready to Publish/);
});
test('candidate popup exposes escaped bounded editing and the existing approve teaching flow',async()=>{
 const {renderClipPreview}=await import('../frontend/js/controllers/clip-preview-controller.js');
 const html=renderClipPreview('candidate','one',{candidates:[{...candidate,start:10,end:48,title:'<script>bad</script>',caption:'<img src=x>'}]});
 assert.match(html,/data-clip-edit-title/);assert.match(html,/maxlength="100"/);assert.match(html,/data-clip-edit-description/);assert.match(html,/data-clip-edit-start/);assert.match(html,/data-clip-edit-end/);
 assert.match(html,/data-clip-action="apply-edits-approve"/);assert.match(html,/Apply edits and approve/);assert.match(html,/Close preview/);
 assert.doesNotMatch(html,/<script>|<img src=x>/);
});
test('reviewed candidates leave the incoming queue and remain re-reviewable in decision history',()=>{
 const html=renderClips({candidates:[candidate,{...candidate,id:'two'}],reviews:[review]});
 const incoming=html.split('data-review-incoming')[1]?.split('data-review-history')[0]??html;
 assert.doesNotMatch(incoming,/data-candidate-id="one"/);
 assert.match(incoming,/data-candidate-id="two"/);
 assert.match(html,/data-review-history/);assert.match(html,/data-clip-preview="one"/);assert.match(html,/data-clip-action="re-review"/);
 assert.doesNotMatch(html,/<video/);
});
test('Publishing opens a scoped popup instead of embedding an HTML preview URL in a video',()=>{
 const html=renderPublishing(undefined,{ready:[candidate],publications:[],published:[]});
 assert.match(html,/data-clip-preview="one"/);assert.match(html,/data-preview-kind="ready"/);assert.doesNotMatch(html,/<video/);
});
test('popup video uses the binary media endpoint and restores the saved Davey controls',async()=>{
 const {renderClipPreview}=await import('../frontend/js/controllers/clip-preview-controller.js');
 const html=renderClipPreview('candidate','one',{candidates:[candidate],reviews:[review]});
 assert.match(html,/src="http:\/\/127\.0\.0\.1:8767\/media\/a{64}"/);
 assert.match(html,/controls playsinline preload="metadata"/);assert.match(html,/data-clip-action="re-review"/);assert.match(html,/data-decision-panel/);
 assert.match(renderClipPreview('ready','one',{ready:[candidate]}),/\/media\/a{64}/);
});
test('popup rejects missing candidates and unsafe preview capabilities',async()=>{
 const {renderClipPreview}=await import('../frontend/js/controllers/clip-preview-controller.js');
 assert.equal(renderClipPreview('candidate','gone',{candidates:[candidate]}),null);
 const html=renderClipPreview('candidate','one',{candidates:[{...candidate,previewUrl:'https://evil.test/private'}]});
 assert.doesNotMatch(html,/evil.test|<video/);assert.match(html,/data-clip-action="approve" disabled/);
});

test('completed trims reset inputs for consecutive metadata edits',async()=>{
 const {resetPreviewTrim}=await import('../frontend/js/controllers/clip-preview-controller.js');
 const start={value:'5',max:'40'},end={value:'25',max:'40'};
 resetPreviewTrim({querySelector:s=>s.includes('start')?start:end},{start:5,end:25});
 assert.deepEqual(start,{value:'0',max:'20'});assert.deepEqual(end,{value:'20',max:'20'});
});
