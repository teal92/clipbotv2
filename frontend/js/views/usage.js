import {postingAllowanceText} from '../subscription-plans.js';
import {escapeHtml as e} from '../ui-utils.js';

import {getUsage,getAccount,getWorkspace} from '../service-state.js';

export function meter(label,used,limit,suffix=''){

 const percent=limit>0?Math.min(100,Math.round(used/limit*100)):0;

 return `<article class="usage-meter"><div><strong>${e(label)}</strong><span>${e(used.toLocaleString())}${suffix} / ${limit>0?e(limit.toLocaleString())+suffix:'No allowance'}</span></div><div class="progress-track" role="progressbar" aria-label="${e(label)}" aria-valuemin="0" aria-valuemax="100" aria-valuenow="${percent}"><span style="width:${percent}%"></span></div><p>${limit>0?e(Math.max(0,limit-used).toLocaleString())+suffix+' remaining':'An active plan is required.'}</p></article>`;

}

export function renderUsage(usage=getUsage()){

 const coverage=getAccount()?.plan.coverage,state=getWorkspace();

 const now=new Date(),year=now.getUTCFullYear(),month=now.getUTCMonth();
 const paidCycle=usage.billingPeriod&&Number.isFinite(usage.billingPeriod.start)&&Number.isFinite(usage.billingPeriod.end)&&usage.billingPeriod.end>usage.billingPeriod.start&&usage.billingPeriod.end-usage.billingPeriod.start<=35*86400?usage.billingPeriod:null;
 const fmt=value=>new Date(value*1000).toLocaleString(undefined,{timeZone:'UTC',timeZoneName:'short'});
 const rangeLabel=paidCycle?`Billing period: ${fmt(paidCycle.start)} – ${fmt(paidCycle.end)}`:usage.periodReconciliationRequired?'Billing period awaiting reconciliation':`${now.toLocaleString(undefined,{month:'long',year:'numeric',timeZone:'UTC'})} · UTC calendar month`;
 const first=paidCycle?new Date(paidCycle.start*1000):new Date(Date.UTC(year,month,1)),last=paidCycle?new Date(paidCycle.end*1000-1):new Date(Date.UTC(year,month+1,0));
 const firstDay=Date.UTC(first.getUTCFullYear(),first.getUTCMonth(),first.getUTCDate()),lastDay=Date.UTC(last.getUTCFullYear(),last.getUTCMonth(),last.getUTCDate()),days=Math.floor((lastDay-firstDay)/86400000)+1;
 const entries=new Map(usage.activity.map(item=>[item.day,item.tokens]));
 const max=Math.max(1,...usage.activity.map(item=>item.tokens));
 const cells=Array.from({length:days},(_,i)=>{const day=new Date(firstDay+i*86400000).toISOString().slice(0,10),tokens=entries.get(day)??0;return `<span tabindex="0" class="activity-cell level-${tokens===0?0:Math.min(4,Math.ceil(tokens/max*4))}" title="${day}: ${tokens.toLocaleString()} tokens" aria-label="${day}: ${tokens.toLocaleString()} tokens"></span>`;}).join('');

 return `<div class="usage-page workspace-page"><section class="section-heading"><div><span class="eyebrow">YOUR ALLOWANCE</span><h2>Davey Usage</h2><p>Actual usage recorded by the server. Daily limits reset in UTC. Paid monthly allowances follow the verified subscription billing period.</p></div><button class="btn" data-account-action="refresh">Refresh Usage</button></section><div class="workspace-stats"><article class="status-card"><span>Input tokens</span><strong>${usage.inputTokens.toLocaleString()}</strong></article><article class="status-card"><span>Output tokens</span><strong>${usage.outputTokens.toLocaleString()}</strong></article><article class="status-card"><span>${paidCycle?'Reviews this billing period':'Recorded reviews this month'}</span><strong>${usage.reviewsMonth.toLocaleString()}</strong></article></div><section class="workspace-card"><p>${e(rangeLabel)}</p>${usage.periodReconciliationRequired?'<p role="status">Billing period awaiting reconciliation; paid AI reviews are paused until verified billing dates are available.</p>':''}${paidCycle&&Number.isInteger(usage.monthlyReviewLimit)?meter('Monthly candidate reviews',usage.reviewsMonth,usage.monthlyReviewLimit):''}${usage.reviewLimit===1000000?`<article class="usage-meter"><strong>Candidate reviews today: ${usage.reviewsToday.toLocaleString()}</strong><p>No fixed review allowance. Spending safeguards and throttling still apply.</p></article>`:meter('Candidate reviews today',usage.reviewsToday,usage.reviewLimit)}${meter('AI allowance used or reserved',(usage.spentMicros+usage.reservedMicros)/1000000,usage.spendLimitMicros/1000000,' USD')}<p>Pending requests reserve allowance before dispatch. Purchases never override the business-wide spending stop.</p></section><section class="workspace-card"><h3>Plan Coverage</h3>${meter('Monitoring scouts',state.sources.length,coverage?.scouts??0)}<p>Favorite streamers: ${coverage?.favorites??0} available - Categories: ${coverage?.categories??0} available.</p><p>Posting allowance: ${coverage?postingAllowanceText(coverage.uniqueClipsDaily):'No active allowance'}. ${state.workerConnected?"Your worker is connected. Monitoring and publishing are not enabled yet.":"Your worker is offline, so no monitoring or posting capacity is being used."}</p></section><section class="workspace-card"><h3>Token Activity</h3><p>${e(rangeLabel)} · daily totals</p><div class="token-activity">${cells}</div><p>${usage.activity.length?'Hover or focus on a day for its token total.':'No Claude token activity recorded yet.'}</p></section><section class="workspace-card"><h3>Spending Protection</h3><p>${usage.aiEnabled?(usage.throttled?'Davey is throttled to protect spending limits.':'Requests remain subject to account and business spending limits.'):'Claude requests are paused. No AI spending is active.'}</p><p data-account-status role="status" aria-live="polite"></p></section></div>`;

}