import {escapeHtml as e} from './ui-utils.js';
import {api,getAccount,getSessionGeneration,refreshWorkspace} from './service-state.js';

export function renderCustomerReadiness(readiness){
 if(!readiness)return '';
 const verified=readiness.emailVerified===true,accepted=readiness.policyAccepted===true;
 return `<section class="workspace-card" data-customer-readiness><h3>Account Verification &amp; Policies</h3><p>Email: ${verified?'Verified':'Verification required'}</p>${verified?'':`<p>${readiness.emailDeliveryAvailable===true?'Send a verification link to your account email. It expires after 15 minutes.':'Verification email is currently unavailable. Contact support before starting paid operations.'}</p><button type="button" class="btn" data-request-verification ${readiness.emailDeliveryAvailable===true?'':'disabled'}>Send Verification Link</button>`}<p>Current policies: ${accepted?'Accepted':'Acceptance required'}</p>${accepted?'':`<form data-accept-policy data-policy-version="${e(readiness.policyVersion??'')}" class="account-form"><label class="customer-policy-authorization"><input type="checkbox" name="acknowledged" required><span>I accept the <a href="/terms" target="_blank" rel="noopener noreferrer">Terms of Service</a> and <a href="/acceptable-use" target="_blank" rel="noopener noreferrer">Acceptable Use Policy</a>, and acknowledge the <a href="/privacy" target="_blank" rel="noopener noreferrer">Privacy Policy</a>.</span></label><button type="submit" class="btn approve">Accept Current Policies</button></form>`}<p data-customer-readiness-status role="status" aria-live="polite"></p></section>`;
}

let connected=false;
export function connectCustomerAccessControls({refresh=()=>{}}={}){
 if(connected)return;connected=true;
 document.addEventListener('click',async event=>{
  const button=event.target.closest('[data-request-verification]');if(!button)return;
  const output=button.closest('[data-customer-readiness]').querySelector('[data-customer-readiness-status]');
  const generation=getSessionGeneration();button.disabled=true;
  try{const data=await api('/api/account/request-verification',{method:'POST',body:{}});if(generation===getSessionGeneration()&&document.contains(output))output.textContent=data.message;}
  catch(error){if(generation===getSessionGeneration()&&document.contains(output))output.textContent=error.message;}
  finally{if(document.contains(button))button.disabled=getAccount()?.readiness?.emailDeliveryAvailable!==true;}
 });
 document.addEventListener('submit',async event=>{
  const form=event.target.closest('[data-accept-policy]');if(!form)return;event.preventDefault();if(!form.reportValidity())return;
  const button=form.querySelector('[type="submit"]'),output=form.closest('[data-customer-readiness]').querySelector('[data-customer-readiness-status]');
  const generation=getSessionGeneration();button.disabled=true;
  try{await api('/api/account/accept-policy',{method:'POST',body:{version:form.dataset.policyVersion}});if(generation!==getSessionGeneration())return;await refreshWorkspace();if(generation===getSessionGeneration())refresh();}
  catch(error){if(generation===getSessionGeneration()&&document.contains(output))output.textContent=error.message;}
  finally{if(document.contains(button))button.disabled=false;}
 });
}
