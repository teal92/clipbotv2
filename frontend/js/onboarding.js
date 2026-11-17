export const SETUP_GUIDE='https://YOUR-GITHUB-USERNAME.github.io/ClipBotV2-setup-guide/';
export function onboardingStep(account={},companion={},connections={}){
 if(account.readiness?.enforced===true&&account.readiness.ready!==true)return 'account';
 const required=companion.requiredVersion??companion.download?.version;
 if(!companion.companionVersion||!['ready','attention','running','starting'].includes(companion.state)||(required&&companion.companionVersion!==required)||companion.errorCode==='tools_missing')return 'companion';
 if(!connections.platforms?.some(x=>['twitch','kick'].includes(x.id)&&x.connected===true&&x.status==='connected'&&x.monitoringReady!==false))return 'connections';
 if(account.readiness&&account.readiness.policyAccepted!==true)return 'policies';
 const sub=account.billing?.subscription;
 const showcase=account.isAdmin===true&&account.plan?.coverage?.ownerShowcase===true;
 if(account.plan?.active!==true||!account.plan.coverage||(!showcase&&(account.billing?.mode!=='live'||sub?.status!=='active'||!Number.isFinite(sub.expires)||sub.expires<=Date.now()/1000)))return 'plan';
 return 'ready';
}
export function renderOnboarding(step){
 const content={policies:['Accept the policies','Read and accept the Terms of Service, Privacy Policy and Acceptable Use Policy before choosing a subscription.','<button class="btn approve" data-onboarding-action="account">Review policies</button>'],account:['Verify your account','Verify your email and accept the current policies before pairing a companion or purchasing a plan.','<button class="btn approve" data-onboarding-action="account">Account verification</button>'],companion:['Install and connect ClipBot Companion','Download and install the companion on this computer. A connected companion is required: a download click alone does not finish setup.',`<a class="btn approve" href="${SETUP_GUIDE}" target="_blank" rel="noopener noreferrer">Open initial setup guide</a><button class="btn" data-onboarding-action="install">Download / connect companion</button>`],connections:['Connect your accounts','Connect Twitch or Kick for monitoring, then connect the social accounts you want to publish to. You can use one streaming service.','<button class="btn approve" data-onboarding-action="connections">Connect Accounts</button>'],plan:['Choose your subscription','Pick a plan to finish setup. Usage unlocks only after confirmed payment. Custom is recommended for choosing capacity that fits your computer and posting needs.','<button class="btn approve" data-onboarding-action="plan">Choose a plan</button>']};
 const item=content[step];if(!item)return '';
 return `<h2 id="onboarding-title">${item[0]}</h2><p>${item[1]}</p><p>Setup: Companion → Connect Accounts → Policies → Plans &amp; Billing</p><div class="onboarding-actions">${item[2]}<button class="btn" data-onboarding-action="check">Check setup progress</button><button class="btn" data-onboarding-action="close">Continue later</button></div><p data-onboarding-status role="status" aria-live="polite"></p>`;
}
