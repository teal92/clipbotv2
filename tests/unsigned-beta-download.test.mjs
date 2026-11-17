import {test} from 'node:test';
import assert from 'node:assert/strict';
import {renderCompanionSetup} from '../frontend/js/views/companion.js';

test('patch update is labeled and preserves explicit unsigned beta acknowledgment',()=>{
 const html=renderCompanionSetup({available:true,url:'/api/companion/download',version:'0.2.9',sha256:'a'.repeat(64),signed:false,unsignedBeta:true,releaseKind:'patch',requiresBetaAcceptance:true},{reason:'update',version:'0.2.8'});
 assert.match(html,/beta patch update/);
 assert.match(html,/Beta patch 0\.2\.9/);
 assert.match(html,/pairing and local data stay in place/);
 assert.match(html,/Stop ClipBot, close the companion/);
 assert.match(html,/data-companion-action="accept-beta"/);
 assert.doesNotMatch(html,/href="\/api\/companion\/download"/);
});

test('unsigned beta explains publisher limitation and requires acknowledgment before showing download',()=>{
 const base={available:true,url:'/api/companion/download',version:'0.2.8',sha256:'a'.repeat(64),signed:false,unsignedBeta:true,requiresBetaAcceptance:true};
 const before=renderCompanionSetup(base);
 assert.match(before,/Unsigned beta/);assert.match(before,/cannot verify YOUR COMPANY NAME as the publisher/);
 assert.match(before,/data-companion-action="accept-beta"/);
 assert.doesNotMatch(before,/href="\/api\/companion\/download"/);
 const after=renderCompanionSetup({...base,requiresBetaAcceptance:false});
 assert.match(after,/Unsigned beta/);assert.match(after,/href="\/api\/companion\/download"/);
 assert.doesNotMatch(after,/data-companion-action="accept-beta"/);
});
