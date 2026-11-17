import {safeMediaUrl} from '../pipeline-utils.js';
import {getWorkspace} from '../service-state.js';
import {escapeHtml as e} from '../ui-utils.js';

export function candidateMediaUrl(candidate){
 try{return candidate.previewFormat==='blurred_fit'?safeMediaUrl(candidate.previewUrl):'';}catch{return '';}
}
export function candidateAttributes(candidate){
 return `data-candidate-id="${e(candidate.id)}" data-platform="${e(candidate.platform)}" data-creator="${e(candidate.creator)}" data-category="${e(candidate.category)}" data-duration="${e(candidate.duration)}" data-davey-score="${e(candidate.score??'')}"`;
}
function reviewRow(candidate,review){
 const preview=candidateMediaUrl(candidate),decision=review?.user_feedback?.decision;
 return `<article class="clip-review-row" ${candidateAttributes(candidate)} ${decision?`data-review-status="${e(decision)}"`:''}><div class="clip-review-info"><h4>${e(candidate.title??candidate.creator??'Clip')}</h4><p>${e(candidate.creator)} · ${e(candidate.platform)} · ${e(candidate.duration)} · Davey score: ${e(candidate.score??'Unscored')}</p>${['approve','reject','hold'].includes(candidate.daveyPrediction)?`<p>Davey predicts: ${e(candidate.daveyPrediction)} · your decision is still required.</p>`:''}${candidate.personalContextUsed===true?'<p>Personal reason counts used for this review.</p>':''}${candidate.belowThreshold?'<p>Below automatic threshold; explicit review required.</p>':''}${review?`<span class="clip-review-badge ${decision==='approve'?'approved':'rejected'}">${decision==='approve'?'Approved':'Rejected'}</span>`:''}${candidate.localFeedbackPending?'<p>Personal feedback pending on this computer.</p>':''}</div><div class="clip-review-actions"><button type="button" class="btn" data-clip-preview="${e(candidate.id)}" data-preview-kind="candidate">${review?'Preview':'Preview & review'}</button>${review?`<button type="button" class="btn" data-clip-action="re-review" data-clip-preview="${e(candidate.id)}" data-preview-kind="candidate" data-preview-review>Re-review</button>`:''}${!preview?'<span class="muted">Local preview is being prepared. Keep the companion running.</span>':''}</div></article>`;
}
export function renderClips(state=getWorkspace()){
 const candidates=state.candidates??[],reviews=state.reviews??[];
 const reviewed=new Map(reviews.filter(r=>r.candidate?.id&&['approve','reject'].includes(r.user_feedback?.decision)).map(r=>[r.candidate.id,r]));
 const incoming=candidates.filter(c=>!reviewed.has(c.id));
 const history=[...reviewed.values()].map(review=>reviewRow(candidates.find(c=>c.id===review.candidate.id)??review.candidate,review)).join('');
 return `<div class="clips-page workspace-page"><section class="section-heading"><div><span class="eyebrow">YOUR CLIPS</span><h2>Clips</h2><p>Open a clip to watch its captioned mobile preview and teach your personal Davey. Reasons and notes stay on your computer.</p></div></section><section class="workspace-card clip-review-queue" data-review-incoming><div class="clip-review-heading"><h3>Ready for your review <span>${incoming.length}</span></h3></div><div class="clip-review-scroll">${incoming.length?incoming.map(c=>reviewRow(c)).join(''):'<p class="clip-review-empty">No clips waiting for review. Keep your companion connected to discover more.</p>'}</div></section><section class="workspace-card clip-review-queue" data-review-history><div class="clip-review-heading"><h3>Decision history <span>${reviewed.size}</span></h3><p>Approved and rejected clips stay here. Reopen any decision to review it again.</p></div><div class="clip-review-scroll">${history||'<p class="clip-review-empty">No saved decisions yet.</p>'}</div></section></div>`;
}
export function renderCandidateDecisionControls() {

  return `

        <div class="candidate-decision">



            <div class="decision-copy">

                <strong>Your decision</strong>



                <span>

                    Your reasons and notes stay on this computer as feedback

                    for your personal Davey.

                </span>

            </div>



            <div class="decision-actions">



                <button

                    class="btn reject"

                    data-clip-action="reject"

                >

                    Reject

                </button>



                <button

                    class="btn approve"

                    data-clip-action="approve"

                >

                    Approve

                </button>



            </div>



        </div>

    `;

}



export function renderDecisionPanel(decision,feedback=null) {
  const local=feedback?.decision===decision?feedback:null;

  const isApprove = decision === "approve";



  const title = isApprove

    ? "Why are you approving this?"

    : "Why are you rejecting this?";



  const reasons = isApprove

    ? [

        "Strong hook",

        "Funny",

        "Great reaction",

        "Good context",

        "Good timing",

        "Right audience",

        "Other",

      ]

    : [

        "Weak hook",

        "Not funny",

        "Needs context",

        "Bad timing",

        "Too long",

        "Weak payoff",

        "Wrong audience",

        "Repetitive",

        "Other",

      ];



  const reasonButtons = reasons

    .map(

      (reason) => `

            <button

                type="button"

                class="decision-reason${local?.reasons?.includes(reason)?' selected':''}"

                data-reason="${reason}"

            >

                ${reason}

            </button>

        `,

    )

    .join("");



  return `

        <div

            class="decision-panel-inner"

            data-decision="${decision}"

        >

            <div class="decision-panel-heading">

                <div>

                    <span class="eyebrow">

                        TEACH DAVEY

                    </span>



                    <h4>${title}</h4>

                </div>

            </div>



            <div class="decision-reasons">

                ${reasonButtons}

            </div>



            <label class="decision-notes">

                <span>Tell Davey more <em>(optional, stored on this computer)</em></span>



                <textarea

                    rows="3"

                    maxlength="1000"

                    placeholder="Explain what Davey should learn from this decision..."

                >${e(local?.justification??'')}</textarea>

            </label>



            <div class="decision-panel-actions">

                <button

                    type="button"

                    class="btn decision-cancel"

                    data-clip-action="cancel-decision"

                >

                    Cancel

                </button>



                <button

                    type="button"

                    class="btn decision-submit ${decision}"

                    data-clip-action="submit-decision"

                >

                    ${

                      isApprove

                        ? "Approve & Teach Davey"

                        : "Reject & Teach Davey"

                    }

                </button>

            </div>

        </div>

    `;

}



export function renderSavedDecision(decision,review={}) {

  const approved = decision === 'approve';

  return `<div class="candidate-decision"><div class="decision-result ${approved?'approved':'rejected'}"><div><strong>${approved?'Approved':'Rejected'}</strong><span>${review.localFeedbackStatus==='confirmed'?'Decision saved to your account. Personal feedback is stored on this computer.':review.localFeedbackStatus==='pending'?'Decision saved to your account. Personal feedback is pending on this computer.':review.localFeedbackStatus==='not_stored'?'Decision saved to your account. Personal feedback was not stored because the local preview is unavailable.':review.localFeedbackStatus==='unavailable'?'Decision saved to your account. Connect the companion to check personal feedback.':'Decision saved to your account. Personal feedback is available through the local companion.'}</span></div><button type="button" class="btn candidate-preview-btn" data-clip-action="re-review">Re-review</button></div></div>`;

}
