import test from 'node:test';
import assert from 'node:assert/strict';
import {renderCompanionSetup,renderCompanionPairing} from '../frontend/js/views/companion.js';

const download={available:true,url:'/api/companion/download',version:'0.2.9',signed:false,sha256:'a'.repeat(64)};
test('download and connect are separate clearly labeled steps with styled actions',()=>{
 const html=renderCompanionSetup(download);
 assert.match(html,/Download &amp; install/);assert.match(html,/Connect companion/);
 assert.match(html,/<div class="companion-actions"><a class="btn approve"[^>]*download>Download for Windows/);
 assert.match(html,/<div class="companion-actions"><button class="btn" data-companion-action="pair">Connect installed companion/);
 assert.match(html,/<footer class="companion-dialog-footer">/);
});
test('beta acknowledgment still prevents access to the download link',()=>{
 const html=renderCompanionSetup({...download,requiresBetaAcceptance:true});
 assert.match(html,/Unsigned beta/);assert.match(html,/data-companion-action="accept-beta"/);
 assert.doesNotMatch(html,/href="\/api\/companion\/download"/);
});
test('open companion is a primary action with a place for the copy control',()=>{
 const html=renderCompanionPairing('sample-pairing-code');
 assert.match(html,/<a class="btn approve" href="clipbot-companion:\/\/pair\?code=sample-pairing-code">Open ClipBot Companion/);
 assert.match(html,/data-pairing-copy-slot/);
 assert.doesNotMatch(html,/<code>/);
});
test('pairing code remains escaped text and encoded URL data',()=>{
 const html=renderCompanionPairing('<img src=x onerror="alert(1)">');
 assert.doesNotMatch(html,/<img/);assert.match(html,/%3Cimg/);
});
