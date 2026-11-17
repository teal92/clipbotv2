import test from 'node:test';
import assert from 'node:assert/strict';
import {loadPipeline,stopPipeline} from '../frontend/js/controllers/pipeline-controller.js';
test('expired pipeline poll transitions back to sign in',async()=>{
 const oldFetch=globalThis.fetch,oldDocument=globalThis.document;
 globalThis.fetch=async()=>({ok:false,status:401,json:async()=>({detail:'Sign in again.'})});
 globalThis.document={activeElement:null};let returned=false;
 const page={isConnected:true,querySelector:()=>null};
 try{await loadPipeline({querySelector:()=>page},()=>{returned=true;});assert.equal(returned,true);}
 finally{stopPipeline();globalThis.fetch=oldFetch;globalThis.document=oldDocument;}
});
import {startPipeline,handlePipelineClick} from '../frontend/js/controllers/pipeline-controller.js';
test('manual refresh uses the saved sign-in transition on expiration',async()=>{
 const oldFetch=globalThis.fetch;let returned=false,ready=false;
 globalThis.fetch=async()=>({ok:false,status:401,json:async()=>({detail:'Sign in again.'})});
 const page={isConnected:true,querySelector:()=>null},root={querySelector:()=>ready?page:null};page.parentElement=root;
 const button={dataset:{pipelineRefresh:''},closest:()=>page};
 try{startPipeline(root,()=>{returned=true;});ready=true;await handlePipelineClick({target:{closest:()=>button}});assert.equal(returned,true);}
 finally{stopPipeline();globalThis.fetch=oldFetch;}
});
