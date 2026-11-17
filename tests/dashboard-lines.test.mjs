import test from 'node:test';import assert from 'node:assert/strict';import {renderDashboardMetrics} from '../frontend/js/dashboard-metrics.js';
test('Davey outcomes uses separate measured lines and keeps accessible data',()=>{
 const html=renderDashboardMetrics({timezone:'UTC',totals:{},buckets:[{key:'2026-10-12',selected:2,notSelected:4,failed:0},{key:'2026-10-13',selected:3,notSelected:1,failed:1}],views:{accounts:[]}});
 const section=html.split('<h3>Davey outcomes</h3>')[1].split('</article>')[0];assert.match(section,/<polyline/);assert.doesNotMatch(section,/<rect /);assert.match(section,/View chart data/);assert.match(section,/Clip selected: 3/);
});
