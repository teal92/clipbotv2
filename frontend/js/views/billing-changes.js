import {getCustomPlan,calculateCustomPrice,CUSTOM_LIMITS} from '../subscription-plans.js';
import {escapeHtml as e} from '../ui-utils.js';
export function renderPlanChange(billing={}){
 const change=billing.change,sub=billing.subscription,sandbox=billing.mode!=='live';
 const states={requested:'Change awaiting confirmation',payment_pending:'Payment pending',scheduled:'Lower limits active; renewal price scheduled',applied:'Plan change applied',expired:'Upgrade payment expired',canceled:'Scheduled downgrade canceled'};
 let payment='';
 if(change?.status==='payment_pending'&&typeof change.paymentUrl==='string'){
  try{const url=new URL(change.paymentUrl);if(url.protocol==='https:'&&url.hostname==='invoice.stripe.com'&&!url.username&&!url.password&&(!url.port||url.port==='443'))payment=`<a class="btn" href="${e(url.href)}" target="_blank" rel="noopener noreferrer">Complete payment</a>`;}catch{}
 }
 const pending=change&&['requested','payment_pending','scheduled'].includes(change.status);
 const retry=change?.status==='requested'&&['starter','creator','pro','custom'].includes(change.plan)?`<p>Stripe has not confirmed this request. Retrying uses the original change and payment request.</p><button type="button" class="btn" data-retry-plan-change="${change.plan}">Retry Plan Change</button>`:'';
 const date=Number.isFinite(change?.effectiveAt)?new Date(change.effectiveAt*1000).toLocaleString(undefined,{timeZone:'UTC',timeZoneName:'short'}):'';
 const receipt=change?`<p role="status"><strong>${e(states[change.status]||'Check billing status')}</strong> · ${e(change.plan||'')}${change.status==='scheduled'?` · ${e(date)}`:''}</p>${payment}${retry}`:'';
 const custom=getCustomPlan(),customPrice=calculateCustomPrice(custom);
 const customInputs=`<div data-custom-change-details hidden><p>Custom: $${customPrice.monthlyPrice}/month · ${custom.scouts} scouts · ${custom.streamerFavorites} streamer favorites · ${custom.categoryFavorites} category favorites · ${custom.dailyReviews} reviews/day. Changes within the same price bucket apply at renewal.</p>${Object.keys(CUSTOM_LIMITS).map(k=>`<input type="hidden" name="custom-${k}" value="${custom[k]}">`).join('')}<input type="hidden" name="quotedMonthlyCents" value="${customPrice.monthlyPrice*100}"><button type="button" class="btn" data-open-custom-builder>Edit Custom capacities</button></div>`;
 return `<section class="billing-change-section">${receipt}${pending?'<p>Resolve this request before choosing another plan.</p>':''}<p data-plan-change-status role="status" aria-live="polite"></p></section>`;
}
