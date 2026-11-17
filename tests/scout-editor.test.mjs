import test from 'node:test';
import assert from 'node:assert/strict';
import * as scouts from '../frontend/js/controllers/scouts-controller.js';
import {renderConnections} from '../frontend/js/views/connections.js';

test('polling keeps the mounted phrase editor, disclosure and unsaved inputs',()=>{
 const editor={details:{open:true},phrase:'unsubmitted phrase',beforeSeconds:27,status:'Saving…'};
 const current={querySelector:()=>editor};
 const next={editor:{details:{open:false},phrase:'no way',beforeSeconds:20},querySelector(){return {replaceWith:form=>{this.editor=form;}};}};
 scouts.preserveTriggerEditor(current,next);
 assert.equal(next.editor,editor);
 assert.equal(next.editor.details.open,true);
 assert.equal(next.editor.phrase,'unsubmitted phrase');
 assert.equal(next.editor.beforeSeconds,27);
 assert.equal(next.editor.status,'Saving…');
});
test('confirmed save replaces the editor so its consent revision refreshes',()=>{
 let replaced=false;
 scouts.preserveTriggerEditor({querySelector:()=>({})},{querySelector:()=>({replaceWith(){replaced=true;}})},true);
 assert.equal(replaced,false);
});

test('connection cards distinguish usable links from missing permissions and destinations',()=>{
 const cases=[['twitch',{connected:true,status:'connected'},'ready'],['kick',{connected:true,status:'permissions_missing'},'attention'],['tiktok',{connected:false,status:'reconnect_required'},'attention'],['instagram',{connected:true,status:'connected',destinationRequired:true},'attention'],['facebook',{connected:false,status:'setup_required'},'attention']];
 for(const [id,state,want] of cases){const html=renderConnections({platforms:[{id,...state}]});const card=html.split(`data-connection-card="${id}"`)[1]?.split('</section>')[0];assert.ok(card,`Card identity missing: ${id}`);assert.match(card,new RegExp(`data-connection-health="${want}"`));}
});
