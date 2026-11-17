import {CUSTOM_LIMITS,getCustomPlan,calculateCustomPrice} from '../subscription-plans.js';
export function renderCustomBuilder(billing={}){
 const custom=getCustomPlan();const quote=calculateCustomPrice(custom);
 return `<h3>Build Your Custom Plan</h3><p>Choose your capacity. Review the server-confirmed monthly price before continuing to secure checkout.</p>
 <form data-workspace-form="custom-plan"><div class="custom-slider-grid">${Object.entries(CUSTOM_LIMITS).map(([name,{label,min,max}])=>`<div class="custom-slider"><div class="custom-slider-heading"><label for="custom-${name}">${label}</label><output for="custom-${name}" data-custom-value="${name}">${custom[name]}</output></div><input type="range" id="custom-${name}" name="${name}" min="${min}" max="${max}" step="1" value="${custom[name]}" data-custom-quantity><div class="custom-range-ends"><span>${min}</span><span>${max}</span></div></div>`).join('')}</div>
 <div class="workspace-notice" data-scout-warning role="status">More scouts increase CPU, memory, disk and internet use on your hardware. Excessive monitoring can cause slowdowns or crashes. Start low and increase only after checking your system.</div>
 <p>Favorites are stored priorities, not additional active scouts. Zero scouts pauses automatic monitoring. Custom has no ClipBot posting cap; actual posting is limited by the connected platform/account and suitable clips. Uploads stay on your hardware. Available platform limits must be checked before publishing.</p>
 <div class="custom-price-summary" aria-live="polite"><span>Monthly price</span><strong data-custom-price>$${quote.monthlyPrice}/month</strong><span data-custom-summary>${custom.dailyReviews} reviews/day · ${quote.monthlyReviews.toLocaleString()} reviews per monthly period · No ClipBot posting cap</span></div>
 <p>Price starts at $7, adds capacity charges for scouts, favorites, daily AI reviews, then rounds up to $5 steps with a $10 Custom minimum and $85 maximum. This price is not an active subscription.</p>
 <button class="btn approve" type="button" data-custom-subscribe >Review price and timing</button><p data-workspace-status role="status" aria-live="polite"></p></form>`;
}
