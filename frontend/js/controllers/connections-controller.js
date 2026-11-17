import {api,resetSession} from '../service-state.js';
import {escapeHtml as e} from '../ui-utils.js';
import {CONNECTION_PLATFORMS,renderConnections,renderConnectionGuide,renderAccountChoices} from '../views/connections.js';
const AUTH_HOSTS={twitch:'id.twitch.tv',kick:'id.kick.com',tiktok:'www.tiktok.com',instagram:'www.facebook.com',facebook:'www.facebook.com'};
export function validatedAuthorizationUrl(platform,value){
 const url=new URL(value);
 if(url.protocol!=='https:'||url.hostname!==AUTH_HOSTS[platform]||url.username||url.password||url.port||url.hash)throw new Error('The platform sign-in address was invalid. Try again.');
 return url.href;
}
export async function loadConnections(container,onUnauthorized){
 const page=container.querySelector('.connections-page');if(!page)return;
 try{const status=await api('/api/connections');if(page.isConnected){
  page.outerHTML=renderConnections(status);
  const query=new URLSearchParams(globalThis.window?.location?.search??'');
  if(query.has('result')){
   const platform=query.get('platform'),state=status.platforms.find(row=>row.id===platform);
   const output=container.querySelector('[data-connections-status]');
   if(output)output.textContent=query.get('result')==='failed'?'The connection was not completed. Try again, or check the platform app settings.':state?.connected?(state.destinationRequired?'Account authorized. Choose your publishing destination below.':'Your account is connected.'): 'The platform connection could not be confirmed. Try again.';
   window.history.replaceState(null,'','/?view=connections');
   if(state?.connected&&state.destinationRequired)container.querySelector(`[data-connection-destinations="${state.id}"]`)?.click();
  }
 }}
 catch(error){if(error.status===401){resetSession();onUnauthorized?.();}else if(page.isConnected)page.querySelector('[data-connections-status]').textContent=error.message;}
}
export function connectConnectionControls({showAuth,authHtml}){
 const fail=(error,output)=>{if(error.status===401){resetSession();showAuth(authHtml());}else output.textContent=error.message;};
 const refresh=page=>loadConnections(page.parentElement,()=>showAuth(authHtml()));
 document.addEventListener('click',async event=>{
  const button=event.target.closest('[data-connection-platform], [data-connection-refresh], [data-connection-close], [data-connection-disconnect], [data-connection-destinations], [data-destination-close], [data-connection-renew]');if(!button)return;
  const page=button.closest('.connections-page');if(!page)return;
  const dialog=page.querySelector('[data-connection-dialog]'),destDialog=page.querySelector('[data-destination-dialog]');
  if(button.matches('[data-connection-close]')){dialog.close();return;}
  if(button.matches('[data-destination-close]')){destDialog.close();return;}
  if(button.matches('[data-connection-refresh]')){button.disabled=true;await refresh(page);button.disabled=false;return;}
  if(button.matches('[data-connection-disconnect], [data-connection-renew]')){
   const platform=button.dataset.connectionDisconnect||button.dataset.connectionRenew;
   const output=page.querySelector('[data-connections-status]');button.disabled=true;
   try{const result=await api(`/api/connections/${platform}/${button.dataset.connectionDisconnect?'disconnect':'refresh'}`,{method:'POST'});await refresh(page);const next=document.querySelector('[data-connections-status]');if(next)next.textContent=result.message||'Connection renewed.';}
   catch(error){fail(error,output);}finally{button.disabled=false;}return;
  }
  if(button.matches('[data-connection-destinations]')){
   button.disabled=true;
   try{const data=await api(`/api/connections/${button.dataset.connectionDestinations}/destinations`);const form=destDialog.querySelector('form');form.dataset.platform=button.dataset.connectionDestinations;form.elements.destinationId.innerHTML=data.destinations.map(row=>`<option value="${e(row.id)}">${e(row.name)}</option>`).join('');form.querySelector('[data-destination-status]').textContent='';destDialog.showModal();}
   catch(error){fail(error,page.querySelector('[data-connections-status]'));}finally{button.disabled=false;}return;
  }
  const platform=CONNECTION_PLATFORMS.find(item=>item.id===button.dataset.connectionPlatform);if(!platform)return;
  const form=dialog.querySelector('form');form.querySelector('[data-connection-account-choices]').innerHTML=renderAccountChoices(platform.id);form.reset();form.dataset.platform=platform.id;form.dataset.available=button.dataset.authorizationAvailable;
  dialog.querySelector('[data-connection-title]').textContent=`Connect ${platform.name}`;
  dialog.querySelector('[data-connection-guide]').textContent='Select your account type above to see its connection guide.';dialog.querySelector('[data-connection-status]').textContent='';dialog.showModal();
 });
 document.addEventListener('change',event=>{const form=event.target.closest('[data-connection-form]');if(!form||event.target.name!=='accountType')return;form.querySelector('[data-connection-guide]').innerHTML=renderConnectionGuide(form.dataset.platform,event.target.value,form.dataset.available==='true');form.querySelector('[data-connection-status]').textContent='';});
 document.addEventListener('submit',async event=>{
  const form=event.target.closest('[data-connection-form], [data-destination-form]');if(!form)return;event.preventDefault();
  const destination=form.matches('[data-destination-form]');
  const button=form.querySelector('[type="submit"]'),output=form.querySelector(destination?'[data-destination-status]':'[data-connection-status]');button.disabled=true;output.textContent=destination?'Saving destination...':'Opening secure platform sign-in...';
  try{
   if(destination){await api(`/api/connections/${form.dataset.platform}/destination`,{method:'POST',body:{destinationId:form.elements.destinationId.value}});form.closest('dialog').close();await refresh(form.closest('.connections-page'));}
   else{const result=await api(`/api/connections/${form.dataset.platform}/start`,{method:'POST',body:{accountType:form.elements.accountType.value}});window.location.assign(validatedAuthorizationUrl(form.dataset.platform,result.authorizationUrl));}
  }catch(error){fail(error,output);}finally{button.disabled=false;}
 });
}
