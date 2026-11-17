// Anonymous, in-memory page activity; no cookies, storage, account or page data.
(() => {
  const nav=globalThis.navigator,doc=globalThis.document;
  if(!doc||!globalThis.crypto?.getRandomValues||nav?.doNotTrack==='1'||nav?.globalPrivacyControl===true)return;
  const visitId=[...crypto.getRandomValues(new Uint8Array(16))].map(n=>n.toString(16).padStart(2,'0')).join('');
  let pending=false,last=0;
  const pulse=async()=>{
    if(pending||doc.hidden||Date.now()-last<55000||nav?.doNotTrack==='1'||nav?.globalPrivacyControl===true)return;
    pending=true;last=Date.now();
    try{await fetch('/api/visitor-presence',{method:'POST',credentials:'omit',headers:{'Content-Type':'application/json'},body:JSON.stringify({visitId}),signal:AbortSignal.timeout(5000)});}catch{}finally{pending=false;}
  };
  pulse();let timer=setInterval(pulse,60000);
  doc.addEventListener('visibilitychange',pulse);
  globalThis.addEventListener?.('pagehide',()=>{clearInterval(timer);timer=null;});
  globalThis.addEventListener?.('pageshow',()=>{if(timer===null){pulse();timer=setInterval(pulse,60000);}});
})();
