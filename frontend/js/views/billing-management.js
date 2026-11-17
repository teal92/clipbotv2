import {escapeHtml as e} from '../ui-utils.js';

export function renderBillingManagement(billing={}){
 const sandbox=billing.mode!=='live',sub=billing.subscription,cancel=billing.cancellation;
 const labels={scheduled:'Cancellation scheduled',reconciliation_required:'Cancellation needs confirmation',canceled:'Subscription canceled'};
 const date=Number.isFinite(cancel?.effectiveAt)?new Date(cancel.effectiveAt*1000).toLocaleString(undefined,{timeZone:'UTC',timeZoneName:'short'}):'';
 const active=!sandbox&&billing.connected===true&&sub?.status==='active'&&Number.isFinite(sub.expires)&&sub.expires>Date.now()/1000;
 return `<section class="workspace-card"><div class="billing-card-heading"><h3>Billing</h3></div><p>${sandbox?'Subscriptions are not available yet.':'Manage your subscription, payment methods and invoices securely.'}</p><details class="billing-details"><summary>Payment methods, invoices and cancellation</summary><p>Cancellation ends ClipBot service immediately and stops future renewal. Remaining paid time and included usage become unavailable. Cancellation does not automatically issue a refund; mandatory legal rights still apply. Earlier cancellations already scheduled under the previous policy keep their stated access-end date.</p>${cancel?`<p role="status"><strong>${e(labels[cancel.status]||'Check cancellation status')}</strong>${cancel.status==='scheduled'&&date?` · Access ends ${e(date)}`:''}</p>${cancel.status==='reconciliation_required'?'<p>ClipBot usage is paused while Stripe cancellation is being confirmed. Renewal cancellation is not yet confirmed. Refresh Billing Status before taking another action.</p>':''}`:''}${!sandbox&&billing.portalAvailable===true?'<button type="button" class="btn" data-billing-portal>Manage Payment Methods &amp; Invoices</button>':'<p>Payment management is not available yet.</p>'}${active&&!cancel?`<form data-cancel-subscription class="account-form"><label class="customer-policy-authorization"><input type="checkbox" name="acknowledged" required><span>I authorize immediate cancellation. My ClipBot service and unused included allowance end now, my subscription will not renew, and no automatic refund is issued. Cancellation overrides any remaining plan-change schedule.</span></label><button type="submit" class="btn">Cancel Subscription Now</button></form>`:''}<button type="button" class="btn" data-account-action="refresh">Refresh Billing Status</button><p data-billing-management-status role="status" aria-live="polite"></p></details></section>`;
}

export function billingRedirectUrl(result,mode,kind='checkout'){
 if(!['test','live'].includes(mode)||typeof result?.sandbox!=='boolean'||result.sandbox!==(mode==='test'))throw Error('Billing mode could not be verified. Refresh your account.');
 if(!['checkout','portal'].includes(kind)||typeof result.url!=='string'||!result.url.length||result.url.length>4096||/[\x00-\x20\x7f]/.test(result.url))throw Error('Invalid billing response.');
 const url=new URL(result.url),host=kind==='portal'?'billing.stripe.com':'checkout.stripe.com';
 if(url.protocol!=='https:'||url.hostname!==host||url.username||url.password||(url.port&&url.port!=='443')||(kind==='portal'&&url.hash))throw Error('Invalid billing response.');
 return url.href;
}
