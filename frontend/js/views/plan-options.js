import {getAccount} from '../service-state.js';

import {renderCustomBuilder} from './custom-plan.js';

import {PLANS,postingAllowanceText} from '../subscription-plans.js';

export function renderPlanOptions(interest,billing=getAccount()?.billing){

 const ready=billing?.connected===true&&billing?.mode==='live';

 return `<div class="workspace-notice">Monthly plans in USD. Review the price, timing and recurring authorization before purchasing or changing your plan. Canceling ends ClipBot access immediately; unused paid time and included allowances become unavailable. Cancellation does not automatically issue a refund; mandatory legal rights apply.</div>

 <section aria-label="Compare plans"><h3>Compare plans</h3><div class="plan-grid">${PLANS.map(plan=>`<button type="button" class="plan-card" ${plan.id==='custom'?'data-open-custom-builder':`data-review-plan="${plan.id}"`} ><span class="eyebrow">${plan.name}</span>${plan.id==='custom'?'<span class="plan-recommended">Recommended</span>':''}<strong class="plan-price">${plan.monthlyPrice===null?'Custom quote':`$${plan.monthlyPrice}<small>/month</small>`}</strong></button>`).join('')}</div><p data-checkout-status role="status" aria-live="polite"></p></section>

 <section class="workspace-card"><h3>Included Usage and Limits</h3><div class="workspace-grid">${PLANS.map(plan=>`<section data-plan-limits="${plan.id}"><h4>${plan.name}</h4>${plan.id==='custom'?'<ul><li>0–40 scouts</li><li>0–25 favorite streamers and 0–25 favorite categories</li><li>12–180 candidate reviews per day</li><li>30 days of selected reviews per monthly period</li><li>No ClipBot posting cap; platform rules apply</li></ul>':`<ul><li>${plan.sources} scouts</li><li>${plan.streamerFavorites} favorite streamers · ${plan.categoryFavorites} favorite categories</li><li>${plan.dailyReviews===null?'No fixed review allowance; fair-use safeguards apply':`${plan.dailyReviews} candidate reviews per day · ${plan.monthlyReviews} reviews per month`}</li><li>${postingAllowanceText(plan.uniqueClipsDaily)}</li></ul>`}</section>`).join('')}</div>

 <p>ClipBot is a hybrid service. Your local worker runs on your computer: it monitors streams, detects activity, transcribes speech, edits and renders clips, and handles media delivery. Video, audio, saved clips and the heavy processing load remain on your hardware. Your computer must have enough storage and processing power and be running for those tasks to work.</p>

 <p>Davey is your personalized ClipBot assistant. Its local worker gathers signals and keeps your personal context. When AI analysis is needed, only the necessary text and signals are sent through the ClipBot service to Claude. Claude runs on Anthropic's servers, not on your computer, and those requests have an API cost. The server provides accounts, subscription access, coordination, updates and usage safeguards; it does not host or relay your video library.</p>

 <p>The service keeps small account, billing, review-decision and usage records. Your personal reason labels and written feedback stay with the companion on your computer. Review your feedback preferences in Streamers before starting analysis or reviewing clips. Shared learning is paused; future contributions will require a separate opt-in. Feedback does not automatically train Claude; shared improvements must be tested before release.</p>

 <p>Scouts are the total monitoring slots across Twitch and Kick. Six scouts can mean three Twitch plus three Kick, or all six on one platform. Favorite streamers and categories prioritize what your scouts watch; they are not extra monitoring slots.</p>

 <p>One AI review evaluates one candidate moment. A review does not guarantee an accepted clip. Retries and extra analyses count toward usage. Starter and Creator include 20 unique clips published per day across all platforms (UTC reset). Posting the same clip to multiple platforms counts once. Failed uploads and retries do not use additional clip allowance. Pro and Custom have no ClipBot posting cap. Platform restrictions still apply. Uploads run directly from your local worker. We will notify you before changes to pricing or included features take effect. Your worker must remain connected through upload completion. A post is successful only after its platform confirms it.</p>

 <p>All plans have daily and monthly review limits. Pro includes 120 reviews/day and 3,600/month; Custom supports up to 180/day and 5,400/month. All tiers require server-enforced limits on billed tokens, retries and total account cost. No automatic overage charges apply. Spending safeguards can pause further reviews when an allowance is reached.</p>

</section>

 <dialog class="pricing-notice account-dialog" data-custom-builder-dialog aria-labelledby="custom-builder-title"><h2 id="custom-builder-title">Custom capacity</h2><section data-custom-plan>${renderCustomBuilder(billing)}</section><button type="button" class="btn" data-account-dialog-close>Close</button></dialog>`;

}

export function renderPlanSummary(){return `<div class="plan-grid">${PLANS.map(plan=>`<section class="plan-card"><h3>${plan.name}</h3><strong>${plan.monthlyPrice===null?'Choose your capacity':`$${plan.monthlyPrice}/month`}</strong></section>`).join('')}</div>`;}
