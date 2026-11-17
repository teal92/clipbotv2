import {renderPlanChange} from '../views/billing-changes.js';
import {bindPasswordPolicy,passwordRequirements} from '../password-policy.js';
import {api,refreshWorkspace,resetSession,getSessionGeneration,getAccount} from '../service-state.js';
import {renderAuth} from '../views/auth.js';
export function selectAccountSection(section,{focus=false}={}){
 const page=document.querySelector('.account-page');if(!page)return false;
 if(!['general','billing','profile','patch-notes'].includes(section))return false;
 for(const tab of page.querySelectorAll('[role="tab"][data-account-tab]')){const selected=tab.dataset.accountTab===section;tab.classList.toggle('active',selected);tab.setAttribute('aria-selected',String(selected));tab.tabIndex=selected?0:-1;if(selected&&focus)tab.focus();}
 for(const panel of page.querySelectorAll('[data-account-panel]'))panel.hidden=panel.dataset.accountPanel!==section;
 return true;
}
export function connectAccountProfileControls({refresh,showAuth}){
 bindPasswordPolicy(document);
 document.addEventListener('focusin',event=>{
  if(!event.target.matches?.('[data-password-security]')||event.target.dataset.securitySeen)return;
  event.target.dataset.securitySeen='true';document.querySelector('[data-account-dialog="security"]')?.showModal();
 });
 document.addEventListener('keydown',event=>{
  const tab=event.target.closest('[role="tab"][data-account-tab]');if(!tab||!['ArrowLeft','ArrowRight','Home','End'].includes(event.key))return;
  event.preventDefault();const tabs=[...tab.closest('[role="tablist"]').querySelectorAll('[role="tab"]')],index=tabs.indexOf(tab);const next=event.key==='Home'?0:event.key==='End'?tabs.length-1:(index+(event.key==='ArrowRight'?1:-1)+tabs.length)%tabs.length;selectAccountSection(tabs[next].dataset.accountTab,{focus:true});
 });
 document.addEventListener('click',async event=>{
  const builder=event.target.closest('[data-open-custom-builder]');if(builder){document.querySelector('[data-custom-builder-dialog]')?.showModal();return;}
  const close=event.target.closest('[data-account-dialog-close]');if(close){close.closest('dialog')?.close();return;}
  const tab=event.target.closest('[data-account-tab]');if(tab){selectAccountSection(tab.dataset.accountTab);return;}
  const remove=event.target.closest('[data-avatar-remove]');if(!remove)return;
  const output=remove.closest('form').querySelector('[data-profile-status]');remove.disabled=true;
  try{await api('/api/account/avatar',{method:'PUT',body:{image:''}});await refreshWorkspace();refresh();selectAccountSection('profile');document.querySelector('[data-account-status]').textContent='Profile picture removed.';}catch(error){output.textContent=error.message;}finally{remove.disabled=false;}
 });
 document.addEventListener('submit',async event=>{
  const form=event.target.closest('[data-profile-form],[data-avatar-form],[data-password-form]');if(!form)return;
  event.preventDefault();const generation=getSessionGeneration();const output=form.querySelector('[data-profile-status]'),button=form.querySelector('[type="submit"]');button.disabled=true;output.textContent='Saving…';
  try{
   if(form.hasAttribute('data-profile-form'))await api('/api/account/profile',{method:'PATCH',body:Object.fromEntries(new FormData(form))});
   else if(form.hasAttribute('data-password-form')){const values=Object.fromEntries(new FormData(form));if(values.newPassword!==values.confirmation)throw Error('New passwords do not match.');const rules=passwordRequirements(values.newPassword);if(!rules.valid)throw Error(rules.errors.join(' '));await api('/api/account/password',{method:'POST',body:{currentPassword:values.currentPassword,newPassword:values.newPassword}});form.reset();}
   else{const file=form.querySelector('[type="file"]').files[0];if(!file||file.size>131072||!['image/jpeg','image/png','image/webp'].includes(file.type))throw Error('Choose a JPEG, PNG or WebP image up to 128 KB.');const encoded=await new Promise((resolve,reject)=>{const reader=new FileReader();reader.onload=()=>resolve(String(reader.result).split(',')[1]);reader.onerror=()=>reject(Error('Could not read this image.'));reader.readAsDataURL(file);});if(generation!==getSessionGeneration()){const error=Error('Account changed. Reload this view.');error.stale=true;throw error;}await api('/api/account/avatar',{method:'PUT',body:{image:encoded}});}
   const password=form.hasAttribute('data-password-form');await refreshWorkspace();refresh();selectAccountSection('profile');document.querySelector('[data-account-status]').textContent=password?'Password changed. Other sessions and local workers were disconnected.':'Profile saved.';
  }catch(error){if(error.status===401){resetSession();showAuth(renderAuth());}else if(!error.stale)output.textContent=error.message;}
  finally{button.disabled=false;}
 });
}
