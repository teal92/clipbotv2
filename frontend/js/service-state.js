import {localFeedbackUrl,boundedFeedback,localFeedbackRequest,mergeLocalFeedback} from './local-feedback.js';
import {isSelectionOutcome} from './selection-outcomes.js';
import {appendActivity,setActivityScope} from './activity.js';
// Account data stays in memory; passwords, sessions and API keys never enter browser storage.
const EMPTY_WORKSPACE={preferences:{usagePreset:'paused',focus:'balanced',avoid:'personal',approval:'review'},sources:[],candidates:[],processing:[],ready:[],published:[],reviews:[],feedbackCount:0,workerConnected:false,aiConfigured:false};
const EMPTY_USAGE={inputTokens:0,outputTokens:0,spentMicros:0,reservedMicros:0,reviewsToday:0,reviewsMonth:0,reviewLimit:0,spendLimitMicros:0,activity:[],aiEnabled:false,throttled:true};
const loggedJobs=new Set();let lastScoutHealth='';
const failures={analysis_paused:'Davey analysis is paused. Enable Davey in Streamers before starting new captures.',analysis_budget:'Davey stopped this review because an analysis spending safeguard was reached. Check your plan allowance and spending limits.',review_limit:'The daily review allowance has been reached. Check Usage before starting more reviews.',analysis_busy:'Davey already has the permitted number of reviews running. This window was not analyzed.',analysis_failed:'Davey analysis did not finish. Check Usage and Logs; automatic paid retries are disabled.',dependency_mismatch:'Local transcription dependencies are incompatible. Update the companion through Start ClipBot.',transcription_unavailable:'The local transcription step failed. Check Processing and update the companion.',queue_full:'Local processing is full. Captures are waiting for processing capacity.',no_speech:'No usable speech was found in this recording.',disk_low:'Your computer needs more free disk space before capturing.',capture_unavailable:'The stream could not be recorded or did not meet the capture-quality setting.',processing_failed:'Local video processing failed. Check Processing and the companion update.'};
let developmentBypass=false,sessionGeneration=0;
export const canBypassSignup=()=>developmentBypass;
let account=null,workspace=structuredClone(EMPTY_WORKSPACE),usage=structuredClone(EMPTY_USAGE);
export const getAccount=()=>account;
export const getSessionGeneration=()=>sessionGeneration;
export const getWorkspace=()=>workspace;
export const getUsage=()=>usage;
function sessionGuard(generation,userId){if(generation!==sessionGeneration||(userId!==undefined&&account?.user?.id!==userId)){const error=Error('Account changed. Reload this view.');error.stale=true;throw error;}}
export async function api(path,{method='GET',body}={}){
 const generation=sessionGeneration;
 const response=await fetch(path,{method,credentials:'same-origin',cache:'no-store',headers:{Accept:'application/json',...(body?{'Content-Type':'application/json'}:{}),...(method!=='GET'?{'X-CSRF-Token':account?.csrfToken??''}:{})},...(body?{body:JSON.stringify(body)}:{})});
 const data=await response.json().catch(()=>({}));
 if(generation!==sessionGeneration){const error=Error('Account changed. Reload this view.');error.stale=true;throw error;}
 if(!response.ok){const error=Error(typeof data.detail==='string'?data.detail:'Please check your entries and try again.');error.status=response.status;throw error;}
 return data;
}
function clearLegacyDrafts(){
 for(const name of ['localStorage','sessionStorage']){
  try{
   const store=globalThis[name];if(!store)continue;
   for(const key of Object.keys(store))if(key.startsWith('clipbot-'))store.removeItem(key);
  }catch{ /* Legacy cache cleanup never blocks real account access. */ }
 }
}
export function resetSession(){setActivityScope(null);loggedJobs.clear();lastScoutHealth='';sessionGeneration++;account=null;workspace=structuredClone(EMPTY_WORKSPACE);usage=structuredClone(EMPTY_USAGE);clearLegacyDrafts();}
export async function loadSession(){
 try{developmentBypass=(await api('/api/auth/options')).developmentBypass===true;}catch{developmentBypass=false;}
 try{account=await api('/api/account');setActivityScope(account?.user?.id);clearLegacyDrafts();if(!signupPending(account))await refreshWorkspace();return true;}
 catch(error){if(error.stale)return false;resetSession();if(error.status===401)return false;throw error;}
}
export async function refreshWorkspace(){
 const generation=sessionGeneration;
 const readinessAccount=await api('/api/account');if(signupPending(readinessAccount)){account=readinessAccount;workspace=structuredClone(EMPTY_WORKSPACE);usage=structuredClone(EMPTY_USAGE);return;}
 const [nextWorkspace,nextUsage]=await Promise.all([api('/api/workspace'),api('/api/usage')]);const nextAccount=readinessAccount;if(generation!==sessionGeneration)return;if(account?.user?.id&&account.user.id!==nextAccount?.user?.id){resetSession();sessionGuard(generation);}await mergeLocalFeedback(nextWorkspace,nextAccount?.user?.id,()=>sessionGuard(generation));sessionGuard(generation);workspace=nextWorkspace;usage=nextUsage;account=nextAccount;setActivityScope(account?.user?.id);for(const job of workspace.pipelineJobs??[])if(job.stage==='failed'&&!isSelectionOutcome(job)&&!loggedJobs.has(job.id)){loggedJobs.add(job.id);appendActivity({id:job.id,level:'error',source:'processing',message:`${job.source?.platform??'Stream'} / ${job.source?.login??'source'}: ${failures[job.errorCode]??'Capture or processing failed. Earlier companion versions did not retain a detailed cause.'}`,createdAt:new Date(Number.isFinite(job.updated)?job.updated*1000:Date.now()).toISOString()});}const companion=workspace.scouts?.companion;const monitored=companion?.monitoredSources??[];const health=(companion?.errorCode??'')+'|'+monitored.map(s=>s.platform+':'+s.login+':'+s.state+':'+s.cueStatus).sort().join('|');if(health!==lastScoutHealth){lastScoutHealth=health;if(companion?.errorCode==='analysis_paused')appendActivity({level:'warning',source:'processing',message:'Enable Davey in Streamers before starting new clip analysis.'});for(const s of monitored)if(s.state==='reconnecting'||s.cueStatus==='waiting_for_processing')appendActivity({level:'warning',source:'processing',message:s.platform+' / '+s.login+': '+(s.state==='reconnecting'?'Stream disconnected. Scout is trying to reconnect.':'Scout is still monitoring; triggered clips are waiting for processing capacity.')});}if(loggedJobs.size>200){for(const id of [...loggedJobs].slice(0,loggedJobs.size-200))loggedJobs.delete(id);}
}
export async function signIn(mode,body){resetSession();account=await api(`/api/auth/${mode}`,{method:'POST',body});if(!signupPending(account))await refreshWorkspace();}
export async function signOut(){await api('/api/auth/logout',{method:'POST'});resetSession();}
export async function saveDavey(body){await api('/api/davey',{method:'PUT',body});await refreshWorkspace();}
export async function saveCandidateReview(event){
 const generation=sessionGeneration,userId=account?.user?.id,guard=()=>sessionGuard(generation,userId);guard();
 const candidate=workspace.candidates?.find(row=>row.id===event.candidate?.id);
 if(!userId||!candidate)throw Error('This candidate is unavailable in your current account.');
 const feedback=boundedFeedback(candidate.id,userId,event.user_feedback);
 let localUrl;try{localUrl=localFeedbackUrl(candidate.previewUrl);}catch{
  if(feedback.decision!=='reject'||feedback.reasons.length||feedback.justification)throw Error('A verified local preview and updated companion are required to save personal feedback. You can reject without reasons or notes until the preview is ready.');
 }
 if(localUrl)await localFeedbackRequest(localUrl,{method:'POST',body:feedback,guard});guard();
 const result=await api('/api/reviews',{method:'POST',body:{candidate_id:candidate.id,decision:feedback.decision,reasons:[],justification:'',localLearning:true}});guard();
 if(localUrl){
  const receipt=result.localFeedbackReceipt;
  if(!receipt||receipt.candidateId!==candidate.id||receipt.userId!==userId||receipt.decision!==feedback.decision||!Number.isSafeInteger(receipt.issuedAt)||typeof receipt.signature!=='string'||!/^[a-f0-9]{64}$/.test(receipt.signature))throw Error('Your decision was saved to your account. Personal feedback remains pending on this computer; keep the companion connected and try saving again.');
  try{await localFeedbackRequest(localUrl+'/confirm',{method:'POST',body:{receipt},guard});guard();}
  catch(error){guard();throw Error('Your decision was saved to your account. Personal feedback remains pending on this computer; keep the companion connected and try saving again.');}
 }
 await refreshWorkspace();guard();return {ok:true,notice:localUrl?'Decision saved. Personal feedback is stored on this computer.':'Decision saved. Personal feedback was not stored because the local preview is unavailable.'};
}

export async function bypassSignup(){resetSession();account=await api('/api/auth/dev-bypass',{method:'POST'});await refreshWorkspace();}


export function signupPending(value=getAccount()){return value?.isAdmin!==true&&value?.readiness?.enforced===true&&value.readiness.ready!==true;}
