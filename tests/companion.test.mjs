import test from 'node:test';
import assert from 'node:assert/strict';
import {renderCompanionStatus,renderCompanionSetup} from '../frontend/js/views/companion.js';
test('header distinguishes requested start from confirmed running',()=>{
 assert.match(renderCompanionStatus({state:'starting',requestedRunning:true}),/Starting/);
 assert.doesNotMatch(renderCompanionStatus({state:'starting',requestedRunning:true}),/>Running</);
 assert.match(renderCompanionStatus({state:'offline',requestedRunning:true}),/Stop ClipBot/);
 assert.match(renderCompanionStatus({state:'ready',requestedRunning:false}),/Ready/);
});
test('setup explains local background processing without fake downloads',()=>{
 const html=renderCompanionSetup({available:false});
 assert.match(html,/system tray/);assert.match(html,/Download for Windows/);assert.match(html,/being prepared/);
 assert.doesNotMatch(html,/href="undefined/);
});

import {companionStartAction} from '../frontend/js/controllers/companion-controller.js';
test('Start distinguishes updates from paused Davey and disconnected companions',()=>{
 assert.equal(companionStartAction({state:'ready',companionVersion:'0.2.2-beta',requiredVersion:'0.2.2-beta'}),'start');
 assert.equal(companionStartAction({state:'attention',errorCode:'analysis_paused',companionVersion:'0.2.2-beta',requiredVersion:'0.2.2-beta'}),'blocked');
 assert.equal(companionStartAction({state:'ready',companionVersion:'0.2.1-beta',requiredVersion:'0.2.2-beta'}),'update');
 assert.equal(companionStartAction({state:'offline'}),'connect');
 assert.equal(companionStartAction({state:'stopping',companionVersion:'0.2.2-beta',requiredVersion:'0.2.2-beta'}),'wait');
 const html=renderCompanionSetup({available:true,version:'0.2.2-beta',url:'/api/companion/download',sha256:'a'.repeat(64)},{reason:'connect'});
 assert.match(html,/already installed/);assert.match(html,/only need the download/);
});
