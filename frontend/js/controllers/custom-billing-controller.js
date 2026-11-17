import {api,getAccount,getSessionGeneration,refreshWorkspace} from '../service-state.js';
import {CUSTOM_LIMITS} from '../subscription-plans.js';
import {escapeHtml as e} from '../ui-utils.js';
import {billingRedirectUrl} from '../views/billing-management.js';
let pending=null;
export function validatedCustomQuote(value,custom){
 if(value?.plan!=='custom'||value.currency!=='USD'||!Number.isInteger(value.monthlyCents)||value.monthlyCents<1000||value.monthlyCents>8500||value.monthlyCents%500||!Number.isInteger(value.monthlyReviews)||value.monthlyReviews!==custom.dailyReviews*30||Object.keys(CUSTOM_LIMITS).some(k=>value.quantities?.[k]!==custom[k]))throw Error('The Custom quote could not be verified. Review your capacities again.');
 return value;
}
export function connectCustomBillingControls(){
 document.addEventListener('click',async event=>{
  const button=event.target.closest('[data-custom-subscribe],[data-review-plan]');if(!button)return;
  const account=getAccount(),session=getSessionGeneration(),form=button.closest('form'),output=form?.querySelector('[data-workspace-status]')??document.querySelector('[data-checkout-status]');
  const plan=button.dataset.reviewPlan??'custom';button.disabled=true;
  try{
   const custom=plan==='custom'?Object.fromEntries(Object.keys(CUSTOM_LIMITS).map(k=>[k,Number(form.elements[k].value)])):undefined;
   const quoted=await api('/api/billing/quote',{method:'POST',body:{plan,...(custom?{custom}:{})}});
   if(custom)validatedCustomQuote(quoted,custom);
   else if(quoted.plan!==plan||quoted.currency!=='USD'||!Number.isInteger(quoted.monthlyCents))throw Error('The plan quote could not be verified.');
   if(session!==getSessionGeneration())return;
   const subscription=account.billing?.subscription,change=subscription?.status==='active'&&Number.isFinite(subscription.expires)&&subscription.expires>Date.now()/1000;
   const available=account.billing?.connected===true&&account.billing.mode==='live'&&(plan!=='custom'||account.billing.customAvailable===true);
   const dialog=document.querySelector('[data-custom-checkout-dialog]');pending={plan,...(custom?{custom,quotedMonthlyCents:quoted.monthlyCents}:{}),session,change};
   const timing=change?`Upgrades activate after successful prorated payment. For a cheaper plan, capacity reductions apply now (capacity increases begin at renewal) and the lower monthly price begins at your next renewal (${e(new Date(subscription.expires*1000).toLocaleDateString())}); no automatic refund. Usage already consumed stays counted.`:'Your plan activates after payment. It renews monthly from the purchase date.';
   dialog.innerHTML=`<h2 id="custom-checkout-title">Review ${e(plan==='custom'?'Custom':plan[0].toUpperCase()+plan.slice(1))} plan</h2><p><strong>$${(quoted.monthlyCents/100).toFixed(2)} USD/month</strong></p>${custom?`<p>${custom.scouts} scouts · ${custom.streamerFavorites} streamer favorites · ${custom.categoryFavorites} category favorites · ${custom.dailyReviews} reviews/day.</p>`:''}<p>${timing}</p><p>Canceling ends ClipBot access immediately. Unused paid time and included allowances become unavailable. Cancellation does not automatically issue a refund; mandatory legal rights apply.</p>${available?'':'<p>Payments are not available yet. No purchase or plan change will be made.</p>'}<form data-custom-checkout-confirm><label><input type="checkbox" name="authorization" required> I authorize the displayed recurring price and plan change.</label><p data-custom-checkout-status role="status"></p><button type="submit" class="btn approve" ${available?'':'disabled'}>${change?'Confirm plan change':'Continue to secure checkout'}</button><button type="button" class="btn" data-custom-checkout-close>Cancel</button></form>`;
   document.querySelector('[data-custom-builder-dialog]')?.close();dialog.showModal();
  }catch(error){if(session===getSessionGeneration()&&output)output.textContent=error.message;}finally{button.disabled=false;}
 });
 document.addEventListener('click',event=>{if(event.target.closest('[data-custom-checkout-close]')){pending=null;document.querySelector('[data-custom-checkout-dialog]')?.close();}});
 document.addEventListener('submit',async event=>{
  const form=event.target.closest('[data-custom-checkout-confirm]');if(!form)return;event.preventDefault();if(!form.reportValidity())return;
  const entry=pending,button=form.querySelector('[type="submit"]'),output=form.querySelector('[data-custom-checkout-status]');
  if(button.disabled||!entry||entry.session!==getSessionGeneration()){output.textContent='Review the plan in your current session first.';return;}
  button.disabled=true;
  try{
   const {session,change,...body}=entry;
   const result=await api(change?'/api/billing/change':'/api/billing/checkout',{method:'POST',body});if(session!==getSessionGeneration())return;
   if(!change)window.location.assign(billingRedirectUrl(result,'live'));
   else {output.textContent=result.status==='scheduled'?'Lower limits are active. The lower price starts at renewal.':result.status==='applied'?'Plan change applied.':result.status==='unchanged'?'You already have these plan capacities.':'Payment or provider confirmation is pending. Check billing status before trying another change.';await refreshWorkspace();document.querySelector('[data-account-action="refresh"]')?.click();}
  }catch(error){if(entry.session===getSessionGeneration())output.textContent=error.message;}finally{button.disabled=false;}
 });
}
