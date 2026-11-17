import {getSessionGeneration} from './service-state.js';

// Keep the short-lived code in this control's closure, never in browser storage.
export function mountPairingCode(container,code,{clipboard=globalThis.navigator?.clipboard,scope=getSessionGeneration,now=Date.now}={}){
 if(typeof code!=='string'||code.length<20||code.length>100)throw Error('Pairing code unavailable. Generate a new code.');
 const generation=scope(),expires=now()+600000;
 container.innerHTML='<div class="pairing-copy-actions"><button type="button" class="btn" data-copy-pairing-code>Copy code</button><span data-pairing-copy-status role="status" aria-live="polite"></span></div><p class="muted">Expires in ten minutes. Keep this code private.</p><details data-manual-pairing hidden><summary>Show code manually</summary><code data-manual-pairing-code></code></details>';
 const button=container.querySelector('[data-copy-pairing-code]'),output=container.querySelector('[data-pairing-copy-status]');
 const active=()=>scope()===generation&&container.isConnected!==false&&button.isConnected!==false&&now()<expires;
 button.addEventListener('click',async()=>{
  if(!active()){output.textContent='Code expired or connection changed. Generate a new code.';return;}
  button.disabled=true;
  try{
   if(typeof clipboard?.writeText!=='function')throw Error('Clipboard unavailable');
   await clipboard.writeText(code);
   if(active()){button.textContent='Copied';output.textContent='Pairing code copied. Paste it in the companion.';}
  }catch{
   if(active()){output.textContent='Clipboard access was blocked. Use the manual option below.';container.querySelector('[data-manual-pairing-code]').textContent=code;container.querySelector('[data-manual-pairing]').hidden=false;}
  }finally{button.disabled=false;}
 });
}
