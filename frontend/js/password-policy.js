const labels=['12–128 characters','Uppercase letter (A–Z)','Lowercase letter (a–z)','Number (0–9)','Special character, such as ! or @','Avoid common passwords'];
export function passwordRequirements(value=''){
 const length=Array.from(value).length;
 const checks=[length>=12&&length<=128,/[A-Z]/.test(value),/[a-z]/.test(value),/[0-9]/.test(value),/[^A-Za-z0-9\s]/u.test(value),! /^(password|qwerty|letmein|welcome|admin|iloveyou|changeme)[0-9]*$/.test(value.toLowerCase().replace(/[^a-z0-9]/g,''))];
 const messages=['Use 12–128 characters.','Add an uppercase letter (A–Z).','Add a lowercase letter (a–z).','Add a number (0–9).','Add a special character, such as ! or @.','Avoid common passwords such as Password123!.'];
 return {checks,valid:checks.every(Boolean),errors:messages.filter((_,index)=>!checks[index])};
}
export function passwordPolicyAttributes(){return 'data-password-policy minlength="12" maxlength="128" pattern="(?=.*[A-Z])(?=.*[a-z])(?=.*[0-9])(?=.*[^a-zA-Z0-9\\s]).{12,128}"';}
export function renderPasswordRules(id){
 return `<div class="password-rules" data-password-rules="${id}"><p data-password-strength role="status" aria-live="polite">Password strength: not entered</p><meter data-password-meter min="0" max="6" value="0" aria-label="Password requirements met"></meter><ul>${labels.map((label,index)=>`<li data-password-rule="${index}"><span data-password-check aria-hidden="true">○</span> ${label}</li>`).join('')}</ul><p class="subtle">Meeting these rules is a basic strength check. Use a unique password or a password manager.</p></div>`;
}
const bound=new WeakSet();
export function bindPasswordPolicy(root=document){
 if(bound.has(root))return;bound.add(root);
 const update=input=>{
  if(!input?.matches?.('[data-password-policy]'))return;
  const result=passwordRequirements(input.value);input.setCustomValidity(input.value&&!result.valid?result.errors.join(' '):'');
  const rules=[...root.querySelectorAll('[data-password-rules]')].find(node=>node.dataset.passwordRules===input.id);if(!rules)return;
  const met=input.value?result.checks.filter(Boolean).length:0;
  const level=!input.value?'not entered':result.valid?'requirements met':met<=2?'weak':'needs improvement';
  rules.querySelector('[data-password-strength]').textContent=`Password strength: ${level}`;rules.querySelector('[data-password-meter]').value=met;
  for(const item of rules.querySelectorAll('[data-password-rule]')){const passed=Boolean(input.value)&&result.checks[Number(item.dataset.passwordRule)];item.classList.toggle('met',passed);item.querySelector('[data-password-check]').textContent=passed?'✓':'○';}
 };
 root.addEventListener('input',event=>update(event.target));
 root.addEventListener('focusin',event=>update(event.target));
 root.addEventListener('reset',event=>queueMicrotask(()=>event.target.querySelectorAll('[data-password-policy]').forEach(update)));
 root.querySelectorAll?.('[data-password-policy]').forEach(update);
}
