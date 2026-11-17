import test from 'node:test';
import assert from 'node:assert/strict';
import {renderAccount} from '../frontend/js/views/account.js';
import {renderCompanionSetup} from '../frontend/js/views/companion.js';
import {selectAccountSection} from '../frontend/js/controllers/account-profile-controller.js';

test('Account exposes accessible persistent patch history with both beta releases',()=>{
 const html=renderAccount({user:{email:'reader@example.com',username:'reader'},plan:{name:'Starter',coverage:null},billing:{}});
 assert.match(html,/data-account-tab="patch-notes"/);
 assert.match(html,/id="account-panel-patch-notes"[^>]*role="tabpanel"/);
 assert.match(html,/0\.2\.10/);assert.match(html,/0\.2\.9/);
 assert.match(html,/Your favorites, ready when live/);
});

test('account controller selects patch notes without an API call',()=>{
 const prior=globalThis.document;const panels=[{dataset:{accountPanel:'general'},hidden:false},{dataset:{accountPanel:'patch-notes'},hidden:true}];
 globalThis.document={querySelector:()=>({querySelectorAll:selector=>selector==='[data-account-panel]'?panels:[]})};
 try{assert.equal(selectAccountSection('patch-notes'),true);assert.equal(panels[0].hidden,true);assert.equal(panels[1].hidden,false);}finally{globalThis.document=prior;}
});

test('0.2.10 popup uses the same customer notes as Account',()=>{
 const popup=renderCompanionSetup({available:false,version:'0.2.10',releaseKind:'patch'},{reason:'update',version:'0.2.9'});
 assert.match(popup,/Your favorites, ready when live/);assert.match(popup,/No reviews for quiet footage/);
 assert.doesNotMatch(popup,/No additional notes/);
});
