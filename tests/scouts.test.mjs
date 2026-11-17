import test from 'node:test';
import assert from 'node:assert/strict';
import {renderStreamers,renderMonitoring,snapshotImage} from '../frontend/js/views/streamers.js';
import {updateSelection,currentDraft,directoryItem,loadScouts,handleScoutsClick,stopScouts} from '../frontend/js/controllers/scouts-controller.js';
const config={running:false,slots:2,forced:[],favorites:[],categories:[]};
const limits={scouts:3,favorites:1,categories:1};
test('scout controls distinguish favorite and forced sources and enforce limits',()=>{
 const a=updateSelection(config,'favorites',{platform:'twitch',login:'channel'},limits);
 assert.equal(a.favorites.length,1);assert.equal(config.favorites.length,0);
 assert.equal(updateSelection(a,'forced',{platform:'twitch',login:'channel'},limits).forced.length,1);
 assert.throws(()=>updateSelection(a,'favorites',{platform:'kick',login:'other'},limits));
 assert.equal(updateSelection(a,'favorites',{platform:'twitch',login:'channel'},limits).favorites.length,0);
});
test('scout source and category displays escape platform text and show real limits',()=>{
 const html=renderStreamers({configuration:config,effective:config,limits},[{platform:'twitch',login:'channel',live:true,categoryName:'<script>bad</script>',viewers:5}],[],null,{},'streamers');
 assert.match(html,/data-scout-controls/);assert.match(html,/Favorite streamer/);assert.match(html,/Favorite/);
 assert.ok(!html.includes('<script>bad'));assert.match(html,/&lt;script&gt;/);
 assert.doesNotMatch(html,/Start monitoring|data-scout-action="test"/);assert.match(html,/data-stream-settings/);
});

test('platform panels stay separate and contain scout controls and forced categories',()=>{
 const html=renderStreamers({configuration:{...config,forcedCategories:[{platform:'kick',id:'42',name:'Game'}]},limits,controls:{sensitivity:'strict',captureGate:'strict',captureSeconds:120,minClipSeconds:15,maxClipSeconds:60}},[{platform:'kick',login:'kickonly',live:true,categoryName:'Game',viewers:30},{platform:'twitch',login:'twitchonly',live:true,categoryName:'Other',viewers:10}],[],null,{},'streamers');
 assert.ok(html.indexOf('data-platform-panel="twitch"')<html.indexOf('data-platform-panel="kick"'));
 const twitch=html.split('data-platform-panel="twitch"')[1].split('data-platform-panel="kick"')[0];assert.match(twitch,/twitchonly/);assert.doesNotMatch(twitch,/kickonly/);
 assert.match(html,/Favorite categories/);assert.match(html,/name="beforeSeconds"/);assert.match(html,/name="chatSpikeMultiplier"/);assert.match(html,/name="afterSeconds"/);assert.doesNotMatch(html,/name="captureSeconds"/);assert.match(html,/name="sensitivity"/);
 assert.doesNotMatch(html,/>Source results</);
 const forced=updateSelection({...config,forcedCategories:[]},'forcedCategories',{platform:'kick',id:'42',name:'Game'},limits);
 assert.equal(forced.forcedCategories.length,1);
 assert.throws(()=>updateSelection({...forced,forced:[{platform:'twitch',login:'one'}]},'forcedCategories',{platform:'kick',id:'43',name:'Another'},limits));
});

test('monitoring uses recent capture evidence and keeps previews unloaded',()=>{
 const now=Date.now()/1000;
 const html=renderMonitoring({configuration:{...config,forced:[{platform:'twitch',login:'channel'}]}},[{platform:'twitch',login:'channel',viewers:123}],{pipelineJobs:[{source:{platform:'twitch',login:'channel'},stage:'capturing',updated:now,created:now-20},{source:{platform:'kick',login:'stale'},stage:'capturing',updated:now-1000},{source:{platform:'twitch',login:'channel'},stage:'ready',updated:now}]});
 assert.match(html,/channel/);assert.match(html,/123/);assert.match(html,/20s/);assert.match(html,/scout-forced/);assert.doesNotMatch(html,/stale/);assert.match(html,/data-scout-preview-src=/);assert.doesNotMatch(html,/<iframe[^>]* src=/);
});
test('streamer directories show both lists and explain controls without replacing zero slots',()=>{
 const html=renderStreamers({configuration:{...config,slots:0},limits},[],[],null,{notice:'Scout controls saved.'},'streamers');
 assert.match(html,/Scout controls saved/);assert.match(html,/role="tooltip"/);assert.match(html,/Top streamers/);assert.match(html,/Top categories/);assert.match(html,/<option value="0" selected/);
});

test('directory actions keep their target when ranking order changes',()=>{
 const refreshed=[{platform:'twitch',login:'newleader'},{platform:'twitch',login:'chosen'},{platform:'kick',login:'chosen'}];
 assert.equal(directoryItem(refreshed,'twitch','chosen'),refreshed[1]);assert.equal(directoryItem(refreshed,'twitch','gone'),undefined);
 assert.equal(directoryItem([{platform:'kick',id:'42'},{platform:'twitch',id:'42'}],'twitch','42','id').platform,'twitch');
});
test('draft read at render time retains edits made during a pending poll',()=>{
 const baseline={slots:2,captureSeconds:120},inputs=[{name:'slots',value:'2'},{name:'captureSeconds',value:'120'}];
 assert.equal(currentDraft(baseline,inputs),null);inputs[1].value='180';assert.deepEqual(currentDraft(baseline,inputs),{slots:'2',captureSeconds:'180'});
});

test('Scouting keeps recent processing and failures visible without calling them active',()=>{
 const now=Date.now()/1000,html=renderMonitoring({configuration:config},[],{pipelineJobs:[{source:{platform:'kick',login:'processing'},stage:'transcribing',created:now-20,updated:now},{source:{platform:'kick',login:'failedsource'},stage:'failed',updated:now},{source:{platform:'kick',login:'processing'},stage:'failed',updated:now-50}]});
 assert.match(html,/Transcribing/);assert.match(html,/Capture or processing failed/);assert.match(html,/0 monitoring now/);assert.doesNotMatch(html,/<iframe/);assert.equal((html.match(/<td>processing<\/td>/g)??[]).length,1);
});

test('Scouting has compact controls while Streamers keeps full setup',()=>{
 const snapshot={configuration:config,limits};
 const watch=renderStreamers(snapshot,[],[],null,{},'scouting'),setup=renderStreamers(snapshot);
 assert.match(watch,/data-monitor-table/);assert.doesNotMatch(watch,/data-scout-controls|data-scout-toggle=/);assert.match(watch,/data-scout-action="allocation"/);assert.doesNotMatch(watch,/data-scout-action="quick-settings"/);
 assert.match(setup,/data-scout-controls/);assert.match(setup,/data-platform-panel/);assert.doesNotMatch(setup,/data-monitor-table/);
});

test('monitoring has no second Start or admin test action',()=>{
 const html=renderStreamers({configuration:config,limits});
 assert.doesNotMatch(html,/data-scout-action="toggle"|data-scout-action="test"|one-hour/);
 assert.match(html,/data-stream-settings/);
});

test('automatic snapshots refresh in thirty second buckets with live players unloaded',()=>{
 const url='https://static-cdn.jtvnw.net/live.jpg';assert.equal(snapshotImage(url,'twitch',31000),snapshotImage(url,'twitch',59000));assert.notEqual(snapshotImage(url,'twitch',59000),snapshotImage(url,'twitch',60000));assert.equal(snapshotImage('https://evil.test/a','twitch'),null);
 const now=Date.now()/1000,html=renderMonitoring({configuration:config,discoveryWarnings:{kick:'Reconnect Kick'}},[{platform:'twitch',login:'a',thumbnailUrl:url}],{pipelineJobs:[{source:{platform:'twitch',login:'a'},stage:'capturing',created:now,updated:now}]});assert.match(html,/<img src=/);assert.match(html,/Go live/);assert.match(html,/Reconnect Kick/);assert.doesNotMatch(html,/<iframe[^>]* src=/);
});

test('Davey and scout controls precede both platform directories',()=>{
 const html=renderStreamers({configuration:config,limits},[],[],null,{},'streamers');
 assert.ok(html.indexOf('data-scout-controls')<html.indexOf('data-platform-panel="twitch"'));
 assert.ok(html.indexOf('data-scout-controls')<html.indexOf('data-platform-panel="kick"'));
});

test('Scouting keeps monitoring tables visible above stream previews',()=>{
 const now=Date.now()/1000,workspace={pipelineJobs:[{source:{platform:'twitch',login:'watcher'},stage:'capturing',created:now-30,updated:now}]};
 const html=renderMonitoring({configuration:config},[{platform:'twitch',login:'watcher',viewers:123}],workspace);
 assert.doesNotMatch(html,/data-tab="scouts"|data-tab="activity"/);assert.doesNotMatch(html,/scout-activity-panel" hidden/);
 assert.ok(html.indexOf('data-monitor-table')<html.indexOf('data-preview-key'));
 assert.match(html,/123 viewers/);assert.match(html,/30s watching/);
 const activity=renderMonitoring({configuration:config},[],workspace,'activity');assert.doesNotMatch(activity,/scout-activity-panel" hidden/);
});
