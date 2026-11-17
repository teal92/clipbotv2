import test from 'node:test';
import assert from 'node:assert/strict';
import {renderDashboardMetrics,activityChart} from '../frontend/js/dashboard-metrics.js';

test('missing views stays unavailable while genuine zero is rendered',()=>{
 const metrics={timezone:'UTC',buckets:[],totals:{approved:0,denied:0,posts:0},postingStreak:0,views:{totalViews:null,observedViews:null,accounts:[{accountKey:'a',platform:'tiktok',name:'Account',views:null,status:'permission_required'}]}};
 const html=renderDashboardMetrics(metrics);
 assert.match(html,/Unavailable/);assert.match(html,/Reconnect and allow analytics permission/);assert.match(html,/not a measured learning improvement/);
 metrics.views.totalViews=0;metrics.views.accounts[0]={...metrics.views.accounts[0],views:0,status:'available'};
 assert.match(renderDashboardMetrics(metrics),/dashboard-views-value">0</);
});
test('all chart inputs and account names are escaped and data is accessible',()=>{
 const html=activityChart([{key:'<img src=x>',approved:4,denied:2}],[['approved','Approved','#35d4ac'],['denied','Denied','#ec8da5']],'Feedback');
 assert.match(html,/&lt;img src=x&gt;/);assert.doesNotMatch(html,/<img/);assert.match(html,/View chart data/);assert.match(html,/Approved: 4/);
 const metrics={buckets:[],totals:{},views:{accounts:[{accountKey:'a',platform:'tiktok',name:'<script>alert(1)</script>',views:null,status:'not_collected'}]}};
 assert.doesNotMatch(renderDashboardMetrics(metrics),/<script>/);
});
test('partial scans display observed count without a complete total',()=>{
 const html=renderDashboardMetrics({buckets:[],totals:{},views:{totalViews:null,observedViews:500,accounts:[{accountKey:'a',platform:'instagram',name:'IG',views:500,status:'partial',stale:false}]}},{accountKey:'a'});
 assert.match(html,/500 observed views/);assert.match(html,/full total is unavailable/);assert.match(html,/Partial scan/);
});
