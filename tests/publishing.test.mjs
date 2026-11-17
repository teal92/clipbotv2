import test from 'node:test';
import assert from 'node:assert/strict';
import {handlePublishingSubmit} from '../frontend/js/controllers/publishing-controller.js';
import {renderPublishing} from '../frontend/js/views/publishing.js';
test('removed preparation drafts never override approved metadata or enter storage',()=>{
 const html=renderPublishing({caption:'</textarea><script>alert(1)</script>',platform:'tiktok'});
 assert.ok(!html.includes('<script>'));assert.ok(!html.includes('data-publishing-form'));assert.ok(!html.includes('name="caption"'));assert.match(html,/No approved clips waiting/);assert.match(html,/data-open-view="connections"/);
});
test('legacy draft submit handler does not write browser storage or publish',()=>{
 const oldStorage=globalThis.sessionStorage;globalThis.sessionStorage={setItem(){assert.fail('Drafts must not be stored');}};
 try{handlePublishingSubmit({target:{closest:()=>({})}});}finally{globalThis.sessionStorage=oldStorage;}
});
