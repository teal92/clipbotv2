import test from 'node:test';
import assert from 'node:assert/strict';
import {renderStreamers,renderMonitoring} from '../frontend/js/views/streamers.js';
import {updateSelection,preserveFavoriteEditors,priorityLookupNames} from '../frontend/js/controllers/scouts-controller.js';

const configuration={running:true,slots:3,forced:[{platform:'twitch',login:'saved'}],forcedCategories:[{platform:'kick',id:'42',name:'Game'}],favorites:[],categories:[]};
const snapshot={configuration,limits:{scouts:3,favorites:1,categories:1},companion:{monitoredSources:[{platform:'twitch',login:'saved',state:'monitoring'},{platform:'twitch',login:'automatic',state:'monitoring'},{platform:'kick',login:'category_pick',state:'monitoring'}]}};

test('each platform has separate favorite entry controls without forced terminology',()=>{
 const html=renderStreamers(snapshot);
 assert.equal((html.match(/data-favorite-entry="streamer"/g)??[]).length,2);
 assert.equal((html.match(/data-favorite-entry="category"/g)??[]).length,2);
 assert.match(html,/Favorite streamers:/);assert.match(html,/Favorite categories:/);
 assert.doesNotMatch(html,/>Forced|>Force monitor|>Force category|>Unforce|Gold: actively/);
 assert.match(html,/Waiting/);
});

test('gold favorite marking follows saved priority identities, including category previews',()=>{
 const rows=[{platform:'twitch',login:'saved',live:true},{platform:'twitch',login:'automatic',live:true},{platform:'kick',login:'category_pick',categoryId:'42',live:true,viewers:10}];
 const html=renderMonitoring(snapshot,rows,{pipelineJobs:[]},'scouts',rows);
 assert.match(html,/Favorite streamer/);assert.match(html,/Favorite category/);
 for(const name of ['twitch:saved','kick:category_pick']){
  const card=html.split(`data-preview-key="${name}"`)[1].split('</article>')[0];assert.match(card,/scout-priority/);
 }
 const automatic=html.split('data-preview-key="twitch:automatic"')[1].split('</article>')[0];assert.doesNotMatch(automatic,/scout-priority/);
 assert.doesNotMatch(html,/Forced streamer|Forced category|Gold: actively/);
});

test('adding an existing favorite is idempotent and cannot remove it',()=>{
 const result=updateSelection(configuration,'forced',{platform:'twitch',login:'saved'},snapshot.limits,{addOnly:true});
 assert.deepEqual(result.forced,configuration.forced);
});

test('favorite lists and category results escape names and preserve removable legacy preferences',()=>{
 const html=renderStreamers({...snapshot,configuration:{...configuration,favorites:[{platform:'kick',login:'legacy'}],categories:[{platform:'kick',id:'55',name:'Old filter'}]}},[],[],null,{kick:{favoriteMatches:{category:[{platform:'kick',id:'4',name:'<img src=x onerror=alert(1)>'}]}}});
 assert.doesNotMatch(html,/<img src=x/);assert.match(html,/&lt;img/);
 assert.match(html,/Other saved preferences/);assert.match(html,/data-scout-remove="favorites"/);assert.match(html,/data-scout-remove="categories"/);
});

test('favorite additions preserve scout capacity checks',()=>{
 assert.throws(()=>updateSelection({...configuration,slots:2},'forced',{platform:'kick',login:'extra'},snapshot.limits,{addOnly:true}));
});

test('polling preserves separate unfinished favorite entry forms',()=>{
 const form={dataset:{favoriteEntry:'streamer',platform:'kick'},draft:'not submitted'};let preserved;
 preserveFavoriteEditors({querySelectorAll:()=>[form]},{querySelector:selector=>{assert.match(selector,/data-platform="kick"/);return {replaceWith:value=>{preserved=value;}};}});
 assert.equal(preserved,form);assert.equal(preserved.draft,'not submitted');
});

test('offline favorites stay first in bounded metadata lookups',()=>{
 const forced=Array.from({length:40},(_,i)=>({platform:'twitch',login:'saved'+i}));
 const active=Array.from({length:40},(_,i)=>({platform:'twitch',login:'auto'+i}));
 const names=priorityLookupNames('twitch',{forced},active,active);
 assert.equal(names.length,65);assert.deepEqual(names.slice(0,40),forced.map(v=>v.login));
 assert.deepEqual(priorityLookupNames('kick',{forced},active),[]);
});
