import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {renderConnections,renderConnectionGuide,renderAccountChoices} from '../frontend/js/views/connections.js';
import {validatedAuthorizationUrl} from '../frontend/js/controllers/connections-controller.js';
import {renderPublishing} from '../frontend/js/views/publishing.js';
import {renderLogs} from '../frontend/js/views/logs.js';
import {renderSettings} from '../frontend/js/views/settings.js';

test('sidebar groups public workflows and keeps Account in the header',()=>{
 const html=readFileSync(new URL('../frontend/index.html',import.meta.url),'utf8');
 const names=[...html.matchAll(/class="nav-item(?: active)?" data-view="([^"]+)"/g)].map(m=>m[1]);
 assert.deepEqual(names,['dashboard','scouting','streamers','clips','processing','publishing','connections','logs','usage','davey','reports']);
 assert.ok(!html.includes('data-view="admin"'));assert.ok(!html.includes('data-view="settings"'));assert.ok(html.includes('class="account-button" data-open-view="account"'));
 const groups=html.split('<div class="nav-divider"></div>');
 assert.ok(groups[1].includes('data-view="connections"'));assert.ok(groups[2].includes('data-view="reports"'));
});
test('all account and worker setup lives in Connect Accounts',()=>{
 const html=renderConnections();
 for(const platform of ['Twitch','Kick','TikTok','Instagram','Facebook'])assert.ok(html.includes(platform));
 assert.ok(html.includes('data-workspace-action="pair-worker"'));
 assert.ok(html.includes('data-workspace-action="check-service"'));
 assert.ok(!renderSettings().includes('data-workspace-action="pair-worker"'));
 assert.ok(!renderLogs().includes('data-workspace-action="check-service"'));
 assert.ok(!renderPublishing().includes('publishing-accounts'));
 assert.ok(renderPublishing().includes('data-open-view="connections"'));
});
test('account type guidance never requests keys or pretends authorization is available',()=>{
 const html=renderConnectionGuide('instagram','personal');
 assert.ok(html.includes('professional'));
 assert.ok(html.includes('not available yet'));
 assert.ok(!html.includes('type="password"'));
 assert.ok(renderConnections().includes('name="accountType"'));
 assert.ok(renderConnectionGuide('twitch').includes('Sign in'));
 assert.ok(!renderConnectionGuide('<script>','personal').includes('<script>'));
});

test('Twitch and Kick developer guides identify required settings and service-owned setup',()=>{
 const twitch=renderConnectionGuide('twitch','developer',true);
 for(const text of ['verified email','two-factor authentication','chat:read','redirect','ClipBot manages'])assert.ok(twitch.includes(text));
 const kick=renderConnectionGuide('kick','developer',true);
 for(const text of ['two-factor authentication','Developer','Enable Webhooks','public HTTPS','user:read','channel:read','ClipBot manages'])assert.ok(kick.includes(text));
 assert.ok(kick.includes('service owner'));
 for(const platform of ['twitch','kick']){
  assert.ok(!renderConnectionGuide(platform,'personal').includes('Enable Webhooks'));
  assert.ok(!renderConnectionGuide(platform,'professional').includes('type="password"'));
 }
});

test('every platform has three distinct account guides with honest minimum requirements',()=>{
 for(const platform of ['twitch','kick','tiktok','instagram','facebook']){
  for(const type of ['personal','professional','developer']){
   const html=renderConnectionGuide(platform,type);
   assert.ok(html.includes('Minimum needed'));
   assert.ok(html.includes('Next steps'));
   assert.ok(html.includes('not available yet'));
  }
 }
 assert.ok(renderConnectionGuide('instagram','personal').includes('Switch'));
 assert.ok(renderConnectionGuide('facebook','personal').includes('Page'));
 assert.ok(renderConnectionGuide('tiktok','developer').includes('private'));
 assert.ok(renderConnectionGuide('twitch','professional').includes('monitoring'));
 assert.ok(!renderConnectionGuide('instagram','<script>').includes('<script>'));
});

test('real connection status renders safely and separates authorization from publishing',()=>{
 const html=renderConnections({workerConnected:false,platforms:[{id:'twitch',connected:true,authorizationAvailable:true,accountName:'<script>Owner</script>',publishingReady:false,status:'connected'}]});
 assert.ok(html.includes('&lt;script&gt;Owner&lt;/script&gt;'));
 assert.ok(html.includes('data-connection-disconnect="twitch"'));
 assert.ok(!html.includes('<script>Owner</script>'));
});

test('authorization redirects only to the selected official platform',()=>{
 assert.ok(validatedAuthorizationUrl('tiktok','https://www.tiktok.com/v2/auth/authorize/?state=test').startsWith('https://www.tiktok.com/'));
 for(const url of ['https://evil.example/','http://www.tiktok.com/','https://user:password@www.tiktok.com/','https://www.tiktok.com:444/'])assert.throws(()=>validatedAuthorizationUrl('tiktok',url));
 assert.throws(()=>validatedAuthorizationUrl('twitch','https://www.tiktok.com/'));
});

test('account choices reflect platform eligibility rather than requiring developer status',()=>{
 const instagram=renderAccountChoices('instagram');
 assert.ok(!instagram.includes('value="personal"'));
 assert.ok(instagram.includes('value="professional"'));
 assert.ok(instagram.includes('professional test account'));
 for(const platform of ['twitch','kick','tiktok']){
  const html=renderAccountChoices(platform);
  for(const type of ['personal','professional','developer'])assert.ok(html.includes(`value="${type}"`));
 }
 const facebook=renderAccountChoices('facebook');
 assert.ok(facebook.includes('Normal account + managed Page'));
 assert.ok(facebook.includes('Creator / Business Page'));
 assert.ok(!facebook.includes('Normal / Personal'));
});

test('Kick linked identity with missing channel scope is visibly incomplete',()=>{
 const html=renderConnections({platforms:[{id:'kick',connected:true,authorizationAvailable:true,accountName:'Kick user',status:'permissions_missing',message:'Approve channel access.'}]});
 assert.match(html,/Channel access missing/);assert.match(html,/Approve channel access/);assert.match(html,/Reconnect Kick/);
});
