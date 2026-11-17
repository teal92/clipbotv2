// Keep the one-time secret in memory; remove it from the URL immediately.
let token=new URLSearchParams(window.location.hash.slice(1)).get('token')??'';
window.history.replaceState(null,'',window.location.pathname);
const form=document.querySelector('[data-email-verification]');
const output=document.querySelector('[data-verification-status]');
if(!/^[A-Za-z0-9_-]{43}$/.test(token)){token='';form.hidden=true;output.textContent='This verification link is invalid. Request a new link from Account.';}
async function accountSession(){
 const response=await fetch('/api/account',{credentials:'same-origin',cache:'no-store',headers:{Accept:'application/json'}});
 if(response.status===401)throw Error('Sign in to the account that requested this link using the sign-in link below, then press Verify Email here.');
 const data=await response.json().catch(()=>({}));
 if(!response.ok||typeof data.csrfToken!=='string'||!data.csrfToken)throw Error('Account access is unavailable. Reload and try again.');
 return data;
}
form.addEventListener('submit',async event=>{
 event.preventDefault();const button=form.querySelector('button');button.disabled=true;output.textContent='Verifying your email…';
 try{
  const session=await accountSession();
  const response=await fetch('/api/account/verify-email',{method:'POST',credentials:'same-origin',cache:'no-store',headers:{'Content-Type':'application/json',Accept:'application/json','X-CSRF-Token':session.csrfToken},body:JSON.stringify({token})});
  const data=await response.json().catch(()=>({}));
  if(!response.ok)throw Error(typeof data.detail==='string'?data.detail:'Verification did not finish. Request a new link from Account.');
  token='';form.hidden=true;output.textContent='Email verified. Return to Account to check policy acceptance and continue.';
 }catch(error){output.textContent=error.message;}finally{button.disabled=false;}
});
