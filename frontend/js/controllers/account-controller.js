import {connectLandingControls} from './landing-controller.js';
import {billingRedirectUrl} from '../views/billing-management.js';
import {bindPasswordPolicy,passwordRequirements} from '../password-policy.js';
import {signIn,signOut,saveDavey,refreshWorkspace,resetSession,bypassSignup,api,getSessionGeneration,getAccount} from '../service-state.js';
import {selectAccountSection} from './account-profile-controller.js';
import {renderAuth} from '../views/auth.js';
export function connectAccountControls({showWorkspace,showAuth,refresh}){
 bindPasswordPolicy(document);
 connectLandingControls(document);
 document.addEventListener('change',event=>{if(event.target.matches?.('[data-plan-change-form] select[name="plan"]')){const form=event.target.closest('form');form.querySelector('[data-custom-change-details]').hidden=event.target.value!=='custom';}});
 document.addEventListener('click',async event=>{
  const portal=event.target.closest('[data-billing-portal]');
  if(portal){
   const generation=getSessionGeneration(),mode=getAccount()?.billing?.mode??'test',output=document.querySelector('[data-billing-management-status]');portal.disabled=true;
   try{const result=await api('/api/billing/portal',{method:'POST'});if(generation!==getSessionGeneration())return;window.location.assign(billingRedirectUrl(result,mode,'portal'));}
   catch(error){if(generation===getSessionGeneration()&&output)output.textContent=error.message;}
   finally{portal.disabled=false;}return;
  }
  const retry=event.target.closest('[data-retry-plan-change]');
  if(retry){
   const generation=getSessionGeneration(),output=document.querySelector('[data-plan-change-status]');retry.disabled=true;
   try{await api('/api/billing/change',{method:'POST',body:{plan:retry.dataset.retryPlanChange,...(retry.dataset.retryPlanChange==='custom'?{custom:getAccount()?.billing?.change?.custom,quotedMonthlyCents:getAccount()?.billing?.change?.monthlyCents}:{})}});if(generation!==getSessionGeneration())return;await refreshWorkspace();if(generation!==getSessionGeneration())return;refresh();selectAccountSection('billing');}
   catch(error){if(generation===getSessionGeneration()&&output)output.textContent=error.message;}
   finally{retry.disabled=false;}
   return;
  }
  const beta=event.target.closest('[data-beta-accept]');
  if(beta){
   beta.disabled=true;
   try{await api('/api/beta/accept',{method:'POST',body:{version:'beta-feedback-v1'}});await refreshWorkspace();refresh();}
   catch(error){if(error.status===401){resetSession();showAuth(renderAuth());}else{const output=document.querySelector('[data-beta-status]');if(output)output.textContent=error.message;}}
   finally{beta.disabled=false;}
   return;
  }
  const checkout=event.target.closest('[data-checkout-plan]');
  if(checkout){
   const generation=getSessionGeneration(),mode=getAccount()?.billing?.mode??'test',output=document.querySelector('[data-checkout-status]');checkout.disabled=true;
   try{const result=await api('/api/billing/checkout',{method:'POST',body:{plan:checkout.dataset.checkoutPlan}});if(generation!==getSessionGeneration())return;window.location.assign(billingRedirectUrl(result,mode));}
   catch(error){if(error.status===401){resetSession();showAuth(renderAuth());}else if(output)output.textContent=error.message;}
   finally{checkout.disabled=false;}
   return;
  }
  const bypass=event.target.closest('[data-dev-bypass]');
  if(bypass){
   bypass.disabled=true;
   try{await bypassSignup();showWorkspace();}
   catch(error){const output=document.querySelector('[data-auth-status]');if(output)output.textContent=error.message;}
   finally{bypass.disabled=false;}
   return;
  }
  const mode=event.target.closest('[data-auth-mode]');
  if(mode){showAuth(renderAuth(mode.dataset.authMode));document.querySelector('#start')?.scrollIntoView({block:'start'});document.querySelector('[data-auth-form] input')?.focus({preventScroll:true});return;}
  const button=event.target.closest('[data-account-action]');
  if(!button)return;
  button.disabled=true;
  try{
   if(button.dataset.accountAction==='logout'){await signOut();showAuth(renderAuth());}
   else{const billingSection=document.querySelector('[data-account-panel="billing"]');const wasBilling=billingSection&&!billingSection.hidden;if(wasBilling)await api('/api/billing/change/refresh',{method:'POST'});await refreshWorkspace();refresh();if(wasBilling)selectAccountSection('billing');}
  }catch(error){if(error.status===401){resetSession();showAuth(renderAuth());}else{const output=document.querySelector('[data-account-status]');if(output)output.textContent=error.message;}}
  finally{button.disabled=false;}
 });
 document.addEventListener('submit',async event=>{
  const cancel=event.target.closest('[data-cancel-subscription]');
  if(cancel){
   event.preventDefault();if(!cancel.reportValidity())return;
   const generation=getSessionGeneration(),button=cancel.querySelector('[type="submit"]'),output=document.querySelector('[data-billing-management-status]');button.disabled=true;if(output)output.textContent='Confirming cancellation with Stripe…';
   try{await api('/api/billing/cancel',{method:'POST',body:{acknowledged:true}});if(generation!==getSessionGeneration())return;await refreshWorkspace();if(generation!==getSessionGeneration())return;refresh();selectAccountSection('billing');}
   catch(error){if(generation===getSessionGeneration()&&output)output.textContent=error.message;}
   finally{button.disabled=false;}return;
  }
  const change=event.target.closest('[data-plan-change-form]');
  if(change){
   event.preventDefault();const generation=getSessionGeneration(),button=change.querySelector('[type="submit"]'),output=document.querySelector('[data-plan-change-status]');
   if(!change.reportValidity())return;
   button.disabled=true;output.textContent='Confirming plan change with Stripeâ€¦';
   try{await api('/api/billing/change',{method:'POST',body:planChangeBody(change)});if(generation!==getSessionGeneration())return;await refreshWorkspace();if(generation!==getSessionGeneration())return;refresh();selectAccountSection('billing');}
   catch(error){if(generation!==getSessionGeneration())return;if(error.status===401){resetSession();showAuth(renderAuth());}else output.textContent=error.message;}
   finally{button.disabled=false;}
   return;
  }
  const auth=event.target.closest('[data-auth-form]'),davey=event.target.closest('[data-davey-form]');
  if(!auth&&!davey)return;
  event.preventDefault();const form=auth??davey;
  const output=form.querySelector(auth?'[data-auth-status]':'[data-davey-status]');
  const button=form.querySelector('[type="submit"]');button.disabled=true;output.textContent='Savingâ€¦';
  try{
   const values=Object.fromEntries(new FormData(form));
   if(auth){if(auth.dataset.authForm==='signup'){const policy=passwordRequirements(values.password);if(!policy.valid)throw Error(policy.errors.join(' '));}await signIn(auth.dataset.authForm,values);form.reset();showWorkspace();}
   else{await saveDavey(values);output.textContent='Davey preferences saved to your account. AI remains subject to server safeguards.';}
  }catch(error){if(!auth&&error.status===401){resetSession();showAuth(renderAuth());}else output.textContent=error.message;}
  finally{button.disabled=false;}
 });
}

export function planChangeBody(form){const values=new FormData(form),plan=values.get('plan');return {plan,...(plan==='custom'?{custom:Object.fromEntries(['scouts','streamerFavorites','categoryFavorites','dailyReviews'].map(k=>[k,Number(values.get('custom-'+k))])),quotedMonthlyCents:Number(values.get('quotedMonthlyCents'))}:{})};}
