import test from 'node:test';
import assert from 'node:assert/strict';
import {saveStreamSettings} from '../frontend/js/stream-settings.js';
test('one settings action saves scouts, clip controls, triggers and preferences in order',async()=>{
 const calls=[],draft={configuration:{slots:2},controls:{sensitivity:'balanced'},triggers:{rules:[]},preferences:{focus:'humor'}};
 await saveStreamSettings(draft,async(path,request)=>{calls.push([path,request.body]);return {};});
 assert.deepEqual(calls.map(c=>c[0]),['/api/scouts/controls','/api/scouts','/api/scouts/triggers','/api/davey']);
 assert.deepEqual(calls.at(-1)[1],draft.preferences);
});
test('partial saves explicitly name the failure and do not claim full success',async()=>{
 let calls=0;
 await assert.rejects(saveStreamSettings({configuration:{},controls:{},triggers:{},preferences:{}},async()=>{if(++calls===3)throw Error('invalid phrase');return {};}),/Clip triggers were not saved.*invalid phrase/);
 assert.equal(calls,3);
});
