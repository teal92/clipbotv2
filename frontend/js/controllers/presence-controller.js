import {api,getAccount} from '../service-state.js';
let presenceTimer=null;
export function stopPresence(){clearInterval(presenceTimer);presenceTimer=null;}
export function startPresence(){stopPresence();let pending=false;const pulse=async()=>{if(pending||globalThis.document?.hidden||!getAccount())return;pending=true;try{await api('/api/presence',{method:'POST'});}catch{}finally{pending=false;}};pulse();presenceTimer=setInterval(pulse,30000);}
