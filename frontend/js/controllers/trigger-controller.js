import {api,getAccount} from '../service-state.js';
import {renderTriggerControls,renderTriggerRule} from '../views/trigger-controls.js';
export async function loadTriggerSettings(){return api('/api/scouts/triggers');}
export async function loadTriggerControls(root,options={}){
 const uid=getAccount()?.user?.id;
 try{const settings=await loadTriggerSettings();if(uid!==getAccount()?.user?.id)return;for(const host of root.querySelectorAll('[data-trigger-controls-host]'))host.innerHTML=renderTriggerControls(settings,options);return settings;}
 catch(error){for(const host of root.querySelectorAll('[data-trigger-controls-host]'))host.textContent=error.message;}
}
export function parseBulkPhrases(text,existing=[]){
 if(typeof text!=='string'||text.length>2000)throw new Error('Use at most 2,000 characters per bulk update.');
 const phrases=text.split(',').map(value=>value.trim()).filter(Boolean);
 if(!phrases.length)throw new Error('Enter phrases separated by commas.');
 if(phrases.some(value=>value.length>80||/[\u0000-\u001f\u007f]/.test(value)))throw new Error('Each phrase must contain 1–80 printable characters.');
 const seen=new Set(existing.map(rule=>rule.phrase.trim().toLowerCase())),added=[];
 for(const phrase of phrases){const key=phrase.toLowerCase();if(seen.has(key))continue;seen.add(key);added.push({phrase,source:'speech',priority:'medium'});}
 if(existing.length+added.length>20)throw new Error('Use at most 20 phrase rules. Nothing was added.');
 return added;
}
export function handleTriggerClick(event){
 const button=event.target.closest('[data-trigger-add],[data-trigger-remove],[data-trigger-bulk-open],[data-trigger-bulk-update]');if(!button)return false;
 const form=button.closest('[data-scout-triggers]');if(!form)return false;
 if(button.matches('[data-trigger-bulk-open]')){const panel=form.querySelector('[data-trigger-bulk]');panel.hidden=!panel.hidden;button.setAttribute('aria-expanded',String(!panel.hidden));if(!panel.hidden)form.querySelector('[data-trigger-bulk-input]').focus();return true;}
 if(button.matches('[data-trigger-bulk-update]')){
  const input=form.querySelector('[data-trigger-bulk-input]'),output=form.querySelector('[data-trigger-status]');
  try{
   const existing=[...form.querySelectorAll('[data-trigger-rule]')].map(row=>({phrase:row.querySelector('[name="phrase"]').value}));
   const added=parseBulkPhrases(input.value,existing);
   form.querySelector('[data-trigger-rules]').insertAdjacentHTML('beforeend',added.map(renderTriggerRule).join(''));
   input.value='';output.textContent=added.length?`${added.length} phrases added. Choose each input and tolerance, then save clip settings.`:'Those phrases are already listed.';
  }catch(error){output.textContent=error.message;}
  return true;
 }
 if(button.matches('[data-trigger-remove]'))button.closest('[data-trigger-rule]').remove();
 else if(form.querySelectorAll('[data-trigger-rule]').length<20)form.querySelector('[data-trigger-rules]').insertAdjacentHTML('beforeend',renderTriggerRule());
 else form.querySelector('[data-trigger-status]').textContent='Use at most 20 phrase rules.';
 return true;
}
export function readTriggerSettings(form){
 const values={};
 for(const name of ['beforeSeconds','afterSeconds','cooldownSeconds','audioRiseDb','chatSpikeMultiplier'])values[name]=Number(form.querySelector(`[name="${name}"]`).value);
 for(const name of ['audioEnabled','speechEnabled','chatEnabled','chatSpikeEnabled'])values[name]=form.querySelector(`[name="${name}"]`).checked;
 values.rules=[...form.querySelectorAll('[data-trigger-rule]')].map(row=>Object.fromEntries(['phrase','source','priority'].map(name=>[name,row.querySelector(`[name="${name}"]`).value])));
 return values;
}
export async function handleTriggerSubmit(event){
 const form=event.target.closest('[data-scout-triggers]');if(!form)return false;event.preventDefault();
 const output=form.querySelector('[data-trigger-status]'),button=form.querySelector('[type="submit"]'),uid=getAccount()?.user?.id;
 button.disabled=true;output.textContent='Saving clip settings…';
 try{await api('/api/scouts/triggers',{method:'PUT',body:readTriggerSettings(form)});if(uid!==getAccount()?.user?.id)return true;output.textContent='Clip settings saved. Active scouts will apply them shortly.';}
 catch(error){output.textContent=error.message;}finally{button.disabled=false;}
 return true;
}
export async function requestManualTrigger(platform,login){return api('/api/scouts/trigger',{method:'POST',body:{platform,login}});}
