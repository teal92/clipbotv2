import {api,getAccount,getSessionGeneration} from '../service-state.js';
import {onboardingStep,renderOnboarding} from '../onboarding.js';
import {selectAccountSection} from './account-profile-controller.js';
import {renderCompanionSetup} from '../views/companion.js';
let navigate=()=>{},generation=0,lastStep='',dismissedStep='',timer=null;
export function stopOnboarding(){generation++;clearTimeout(timer);timer=null;lastStep='';document.querySelector('[data-onboarding-dialog]')?.close();}
export async function checkOnboarding({show=true,force=true}={}){
 const session=getSessionGeneration(),epoch=generation,account=getAccount();if(!account)return 'blocked';
 const [companion,connections]=await Promise.all([api('/api/companion/status'),api('/api/connections')]);
 if(session!==getSessionGeneration()||epoch!==generation)return 'blocked';
 const step=onboardingStep(account,companion,connections),dialog=document.querySelector('[data-onboarding-dialog]');
 // The existing private owner workflow remains available while live release is gated.
 if(account.isAdmin===true&&step==='plan')return 'ready';
 document.querySelector('.setup-guide')?.classList.toggle('setup-required',step==='companion');
 if(show&&dialog&&(force||dismissedStep!==step)){if(step==='ready'){dialog.close();lastStep='';}else{if(lastStep!==step||!dialog.open){dialog.innerHTML=renderOnboarding(step);lastStep=step;}if(!dialog.open&&!document.querySelector('[data-companion-dialog]')?.open)dialog.showModal();}}
 return step;
}
export function startOnboarding(){
 stopOnboarding();dismissedStep='';const epoch=generation;
 const poll=async()=>{try{await checkOnboarding({force:false,show:!getAccount()?.plan?.active||!!document.querySelector('[data-onboarding-dialog]')?.open});}catch(error){const output=document.querySelector('[data-onboarding-status]');if(output)output.textContent=error.status===401?'Please sign in again.':'Setup status could not be checked. Try again.';}if(epoch===generation&&getAccount())timer=setTimeout(poll,15000);};poll();
}
export function connectOnboardingControls(renderView){
 navigate=renderView;
 document.querySelector('[data-onboarding-dialog]')?.addEventListener('cancel',()=>{dismissedStep=lastStep;});
 document.addEventListener('click',async event=>{
  const button=event.target.closest('[data-onboarding-action]');if(!button)return;
  const dialog=document.querySelector('[data-onboarding-dialog]'),action=button.dataset.onboardingAction;
  if(action==='close'){dismissedStep=lastStep;dialog.close();return;}
  if(action==='check'){button.disabled=true;try{await checkOnboarding();}catch{dialog.querySelector('[data-onboarding-status]').textContent='Could not check setup. Try again.';}finally{button.disabled=false;}return;}
  dismissedStep=lastStep;dialog.close();
  if(action==='install'){
   const session=getSessionGeneration();button.disabled=true;try{const state=await api('/api/companion/status');const companion=document.querySelector('[data-companion-dialog]');if(session!==getSessionGeneration()||!getAccount())return;companion.innerHTML=renderCompanionSetup(state.download);companion.showModal();}catch{if(session!==getSessionGeneration()||!getAccount())return;dialog.innerHTML=renderOnboarding('companion');dialog.querySelector('[data-onboarding-status]').textContent='Could not load the installer. Try again.';dialog.showModal();}finally{button.disabled=false;}
  }
  if(action==='account'){navigate('account');selectAccountSection('general');}
  if(action==='connections')navigate('connections');
  if(action==='plan'){navigate('account');selectAccountSection('billing');document.querySelector('[data-custom-builder-dialog]')?.showModal();}
 });
}
