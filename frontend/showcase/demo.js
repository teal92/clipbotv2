import {renderDashboard} from '../js/views/dashboard.js';
import {renderDashboardMetrics} from '../js/dashboard-metrics.js';
import {renderMonitoring} from '../js/views/streamers.js';
const now=Date.now()/1000;
const sources=[{platform:'twitch',login:'nova_arcade',categoryName:'Competitive gaming',categoryId:'arena'},{platform:'kick',login:'midnight_coop',categoryName:'Co-op adventures',categoryId:'coop'},{platform:'twitch',login:'wildtrail_live',categoryName:'Open-world exploration',categoryId:'world'}];
const monitors=sources.map((s,i)=>({...s,state:'monitoring',started:now-386-i*155,chunks:6+i,spikes:3+i,cueStatus:i===0?'saving_clip':'watching_for_cues',chatStatus:'connected',speechStatus:'sampling',interaction:{samples:Array.from({length:24},(_,n)=>({at:now-(23-n)*5,audioDb:-45+Math.round(14*Math.sin(n*.9+i)),chatMessages:4+Math.round(9*Math.abs(Math.sin(n*.6+i)))+(n===19?25:0),cues:n===19?['chat_spike','capture']:n===15?['audio_rise']:[]}))}}));
const candidates=sources.map((s,i)=>({id:'demo-clip-'+i,creator:s.login,platform:s.platform,category:s.categoryName,title:['The last-second comeback','When the whole team commits','The view was worth the climb'][i],duration:['00:28','00:34','00:22'][i],score:[94,88,91][i],daveyPrediction:'approve'}));
const jobs=sources.flatMap((s,i)=>Array.from({length:3+i},(_,j)=>({id:`demo-${i}-${j}`,source:s,stage:j===0?'capturing':j===1?'analyzing':'ready',created:now-300-j*20,updated:now-3})));
const workspace={sources,candidates,processing:[{},{}],published:Array.from({length:12},()=>({status:'published'})),pipelineJobs:jobs,reviews:[],workerConnected:true};
const snapshot={configuration:{running:true,slots:3,forced:[sources[0]],forcedCategories:[],platformSlots:{twitch:2,kick:1}},limits:{scouts:3},companion:{monitoredSources:monitors}};
const metrics={timezone:'UTC',totals:{approved:32,denied:9,posts:12},postingStreak:4,feedbackMeaning:'Sample creator activity. These values are invented for this demonstration.',buckets:Array.from({length:7},(_,i)=>({key:'2026-10-'+(11+i),approved:[2,5,3,7,4,6,5][i],denied:[1,0,2,1,2,1,2][i],selected:[4,7,5,8,6,8,9][i],notSelected:[2,2,3,2,3,1,2][i],failed:[0,0,1,0,0,0,0][i],posts:[1,2,1,3,2,2,1][i]})),views:{totalViews:null,observedViews:null,accounts:[]}};
const container=document.querySelector('#demo-content');
const notice='<div class="demo-banner">Illustrative workspace · all counts, streamer names and scout signals below are sample data.</div>';
function render(view){
 document.querySelector('#demo-title').textContent={dashboard:'Dashboard',scouting:'Scouting'}[view];
 document.querySelectorAll('[data-demo-view]').forEach(b=>b.classList.toggle('active',b.dataset.demoView===view));
 if(view==='dashboard'){
  container.innerHTML=notice+renderDashboard(workspace);
  container.querySelector('[data-dashboard-metrics]').outerHTML=renderDashboardMetrics(metrics);
  container.querySelector('.section-heading p').textContent='A sample creator session, from discovery to your review queue.';
  container.querySelector('.dashboard-metrics-heading p').textContent='Sample review decisions and example posting activity.';
  container.querySelector('[data-open-view=clips]')?.closest('.workspace-card')?.remove();
 }else if(view==='scouting'){
  container.innerHTML=notice+'<div class="workspace-page"><section class="section-heading"><div><span class="eyebrow">SEE THE WORKFLOW</span><h2>Three scouts. One workspace.</h2><p>Simulated capture cues, audio signals and review-ready moments.</p></div><div class="demo-kpis"><strong>3 sample feeds</strong></div></section>'+renderMonitoring(snapshot,sources.map((s,i)=>({...s,live:true,viewers:[1240,680,920][i]})),workspace)+'</div>';
  container.querySelectorAll('.scout-snapshot').forEach((box,i)=>box.innerHTML=`<div class="demo-frame frame-${['one','two','three'][i]}"><span>ILLUSTRATIVE DEMO FEED</span><strong>${['THE LAST-SECOND<br>COMEBACK.','BETTER<br>TOGETHER.','TAKE THE<br>SCENIC ROUTE.'][i]}</strong><small>Sample visual · no actual gameplay</small></div>`);
 }
 container.querySelectorAll('[data-open-view]').forEach(b=>{const view={streamers:'scouting'}[b.dataset.openView];if(view)b.onclick=()=>render(view);else{b.disabled=true;b.title='Account connections are available in your real workspace after sign-in.';}});
 container.querySelectorAll('[data-scout-action="manual"]').forEach(b=>b.onclick=()=>{b.textContent='Sample clip queued ✓';b.disabled=true;});
 container.querySelectorAll('[data-scout-action="allocation"]').forEach(b=>{b.disabled=true;b.title='Sample allocation only';});
 container.querySelectorAll('[data-pipeline-refresh],[data-dashboard-period],[data-dashboard-refresh-views]').forEach(b=>{b.disabled=true;b.title='Static sample data in this preview';});
 history.replaceState(null,'','#'+view);
}
document.querySelectorAll('[data-demo-view]').forEach(b=>b.onclick=()=>render(b.dataset.demoView));
render(['dashboard','scouting'].includes(location.hash.slice(1))?location.hash.slice(1):'dashboard');
