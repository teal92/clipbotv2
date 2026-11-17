// Private teaching notes travel only to the fixed local companion, never the cloud.
export const FEEDBACK_REASONS=Object.freeze(['Strong hook','Funny','Great reaction','Good context','Good timing','Right audience','Other','Weak hook','Not funny','Needs context','Bad timing','Too long','Weak payoff','Wrong audience','Repetitive']);
export function localFeedbackUrl(value){
 const url=new URL(value);
 if(url.protocol!=='http:'||url.hostname!=='127.0.0.1'||url.port!=='8767'||url.username||url.password||url.search||url.hash||!/^\/(preview|media)\/[a-f0-9]{64}$/.test(url.pathname))throw Error('A verified local preview is required to save personal feedback.');
 return 'http://127.0.0.1:8767/feedback/'+url.pathname.split('/')[2];
}
export function boundedFeedback(candidateId,userId,feedback){
 if(!['approve','reject'].includes(feedback?.decision))throw Error('Choose approve or reject.');
 if(!Array.isArray(feedback.reasons)||feedback.reasons.length>FEEDBACK_REASONS.length||feedback.reasons.some(reason=>!FEEDBACK_REASONS.includes(reason))||typeof feedback.justification!=='string'||feedback.justification.length>1000)throw Error('Choose listed reasons and keep personal notes under 1,000 characters.');
 return {candidateId,userId,decision:feedback.decision,reasons:[...new Set(feedback.reasons)],justification:feedback.justification};
}
export async function localFeedbackRequest(url,{method='GET',body,guard}={}){
 guard();
 let response,data;
 try{
  response=await fetch(url,{method,mode:'cors',credentials:'omit',cache:'no-store',redirect:'error',referrerPolicy:'no-referrer',signal:AbortSignal.timeout(2500),headers:{Accept:'application/json',...(body?{'Content-Type':'application/json'}:{})},...(body?{body:JSON.stringify(body)}:{})});
  guard();data=await response.json();guard();
 }catch(error){guard();throw Error('Personal feedback could not be saved on this computer. Keep the updated companion running and try again.');}
 if(!response.ok||method==='POST'&&data?.ok!==true){const error=Error('Personal feedback could not be saved on this computer. Update the companion and try again.');error.localStatus=response.status;throw error;}
 return data;
}
export function validLocalFeedback(value,candidateId,userId){
 if(!value||value.candidateId!==candidateId||value.userId!==userId||typeof value.confirmed!=='boolean')return null;
 try{return {...boundedFeedback(candidateId,userId,value),confirmed:value.confirmed};}catch{return null;}
}
export async function mergeLocalFeedback(state,userId,guard){
 const candidates=state.candidates??[],reviews=state.reviews??[];
 const targets=candidates.flatMap(candidate=>{try{return [{candidate,url:localFeedbackUrl(candidate.previewUrl)}];}catch{return [];}});
 const unavailable=candidate=>{candidate.localFeedbackUnavailable=true;const review=reviews.find(row=>row.candidate?.id===candidate.id);if(review)review.localFeedbackStatus='unavailable';};
 const apply=(candidate,data)=>{
  guard();const feedback=validLocalFeedback(data.feedback,candidate.id,userId);if(!feedback)return;
  const review=reviews.find(row=>row.candidate?.id===candidate.id);
  if(feedback.confirmed&&review?.user_feedback?.decision===feedback.decision){review.user_feedback={decision:feedback.decision,reasons:feedback.reasons,justification:feedback.justification};review.localFeedbackStatus='confirmed';}
  else if(!feedback.confirmed){candidate.localFeedbackPending=feedback;if(review)review.localFeedbackStatus='pending';}
 };
 // Probe once before fan-out: an offline companion cannot stall 200 retained clips.
 const first=targets.shift();if(!first)return state;
 try{apply(first.candidate,await localFeedbackRequest(first.url,{guard}));}
 catch(error){guard();unavailable(first.candidate);if(!Number.isInteger(error.localStatus)){for(const {candidate} of targets)unavailable(candidate);return state;}}
 // Four reads at a time bound companion load; private data stays in account-scoped memory.
 for(let index=0;index<targets.length;index+=4){
  await Promise.all(targets.slice(index,index+4).map(async({candidate,url})=>{
   try{apply(candidate,await localFeedbackRequest(url,{guard}));}
   catch(error){guard();unavailable(candidate);}
  }));guard();
 }
 return state;
}
