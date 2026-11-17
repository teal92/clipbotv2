import test from 'node:test';
import assert from 'node:assert/strict';
import {existsSync,readFileSync} from 'node:fs';
import {renderBigDavey} from '../frontend/js/views/big-davey.js';
import {renderBetaFeedback} from '../frontend/js/views/beta-feedback.js';

test('private owner metrics have no public dashboard assets or browser endpoint',()=>{
 assert.equal(existsSync(new URL('../frontend/js/views/admin.js',import.meta.url)),false);
 assert.equal(existsSync(new URL('../frontend/js/controllers/admin-controller.js',import.meta.url)),false);
 const app=readFileSync(new URL('../frontend/js/app.js',import.meta.url),'utf8');
 assert.ok(!app.includes('renderAdmin'));assert.ok(!app.includes('/api/admin/metrics'));
});
test('beta notice discloses local feedback and paused shared learning',()=>{
 const html=renderBetaFeedback({accepted:false,required:true,version:'beta-feedback-v1'});
 assert.ok(html.includes('on your computer'));assert.ok(html.includes('Shared learning is paused'));assert.ok(html.includes('bounded'));assert.ok(!html.includes('cannot be switched off'));
 assert.ok(html.includes('data-beta-accept'));
 assert.ok(html.includes('Private media'));
 assert.ok(!html.includes('type="checkbox"'));
 const accepted=renderBetaFeedback({accepted:true,required:true,version:'beta-feedback-v1'});
 assert.ok(!accepted.includes('data-beta-accept'));
 assert.ok(accepted.includes('Acknowledged'));
});

import {learningProgress} from '../frontend/js/views/big-davey.js';
test('learning progress tracks evidence targets without inventing accuracy',()=>{
 assert.equal(learningProgress(250,1000),25);
 assert.equal(learningProgress(2000,1000),100);
 assert.equal(learningProgress(-1,1000),0);
 const html=renderBigDavey({sharedDecisions:250,feedbackReasons:{Funny:8},learning:{decisionTarget:1000,betaParticipants:3,participantTarget:10,reasonCoverage:1},platformPosts:{},generatedAt:0});
 assert.ok(html.includes('aria-valuenow="25"'));
 assert.ok(html.includes('Not measured'));
 assert.ok(html.includes('Precision'));
 assert.ok(html.includes('Recall'));
 assert.ok(html.includes('not an intelligence'));
 assert.ok(html.includes('COLLECTION PAUSED'));assert.ok(!html.includes('GATHERING EVIDENCE'));
});
