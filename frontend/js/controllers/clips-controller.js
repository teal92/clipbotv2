// ==========================================================
// ClipBot SaaS
// Clips Controller
// ==========================================================
//
// Handles user interaction on the Clips page.
// Rendering stays in views/clips.js.

import {closeClipPreview,applyPreviewEdits} from "./clip-preview-controller.js";
import { renderClips, renderDecisionPanel, renderCandidateDecisionControls, renderSavedDecision } from "../views/clips.js";
import {saveCandidateReview,getWorkspace,getAccount} from "../service-state.js";
import { appendActivity } from "../activity.js";

export async function handleClipsClick(event) {
  const actionButton = event.target.closest("[data-clip-action]");
  const reasonButton = event.target.closest("[data-reason]");

  const workspaceTab = event.target.closest("[data-clips-tab]");

  if (workspaceTab) {
    switchClipsWorkspace(workspaceTab);
    return;
  }

  // Quick-reason tags can be selected independently.
  if (reasonButton) {
    reasonButton.classList.toggle("selected");
    return;
  }

  // Ignore clicks that do not belong to Clips controls.
  if (!actionButton) {
    return;
  }

  let action = actionButton.dataset.clipAction;

  const candidateCard = actionButton.closest(".candidate-card");

  if (!candidateCard) {
    return;
  }

  const decisionPanel = candidateCard.querySelector("[data-decision-panel]");

  if (!decisionPanel) {
    return;
  }

  if (action === 're-review') {
    candidateCard.querySelector('.candidate-decision').outerHTML = renderCandidateDecisionControls().replace('data-clip-action="approve"',candidateCard.querySelector('video')?'data-clip-action="approve"':'data-clip-action="approve" disabled');
    decisionPanel.innerHTML = '';
    decisionPanel.hidden = true;
    return;
  }

  if(action==='apply-edits-approve'){
    const button=actionButton;button.disabled=true;
    try{await applyPreviewEdits(candidateCard);action='approve';}
    catch(error){candidateCard.querySelector('[data-clip-edit-status]').textContent=error.message;return;}
    finally{button.disabled=false;}
  }
  // Open the correct Davey teaching panel.
  if (action === "approve" || action === "reject") {
    const state=getWorkspace(),id=candidateCard.dataset.candidateId;
    const feedback=state.candidates?.find(row=>row.id===id)?.localFeedbackPending??state.reviews?.find(row=>row.candidate?.id===id)?.user_feedback;
    decisionPanel.innerHTML = renderDecisionPanel(action,feedback);
    decisionPanel.hidden = false;

    return;
  }

  // Close the teaching panel without saving anything.
  if (action === "cancel-decision") {
    decisionPanel.innerHTML = "";
    decisionPanel.hidden = true;

    return;
  }

  // Save bounded feedback locally before confirming the review.
  if (action === "submit-decision") {
    const learningEvent = buildLearningEvent(candidateCard, decisionPanel);

    const reviewingUser=getAccount()?.user?.id;
    let saved;
    actionButton.disabled=true;
    try{saved=await saveCandidateReview(learningEvent);}catch(error){saved={ok:false,error:error.message};}
    finally{actionButton.disabled=false;}
    if (getAccount()?.user?.id!==reviewingUser||!candidateCard.isConnected) return;
    if (!saved.ok) {
      let output = decisionPanel.querySelector('[data-review-status]');
      if (!output) {
        output = document.createElement('p');
        output.dataset.reviewStatus = '';
        output.setAttribute('role', 'status');
        decisionPanel.appendChild(output);
      }
      output.textContent = saved.error;
      return;
    }
    appendActivity({ level:'info', source: 'davey', message: `Candidate review saved to your account: ${learningEvent.user_feedback.decision}. Personal feedback stays on this computer.` });

    finalizeCandidateDecision(candidateCard, decisionPanel, learningEvent, saved);

    return;
  }
}

function buildLearningEvent(candidateCard, decisionPanel) {
  const decisionInner = decisionPanel.querySelector("[data-decision]");

  const selectedReasons = [
    ...decisionPanel.querySelectorAll(".decision-reason.selected"),
  ].map((button) => button.dataset.reason);

  const justification =
    decisionPanel.querySelector("textarea")?.value.trim() || "";

  const daveySignals = [
    ...candidateCard.querySelectorAll("[data-davey-signal]"),
  ].map((signal) => signal.dataset.daveySignal);

  const daveyReason =
    candidateCard.querySelector("[data-davey-reason]")?.textContent.trim() ||
    "";

  return {
    event_type: "clip_review",

    candidate: {
      id: candidateCard.dataset.candidateId,
      platform: candidateCard.dataset.platform,
      creator: candidateCard.dataset.creator,
      category: candidateCard.dataset.category,
      duration: candidateCard.dataset.duration,
    },

    davey_prediction: {
      confidence: Number(candidateCard.dataset.daveyScore),
      explanation: daveyReason,
      signals: daveySignals,
    },

    user_feedback: {
      decision: decisionInner?.dataset.decision || null,

      reasons: selectedReasons,

      justification: justification,
    },

    adjustments: {
      trim_start: null,
      trim_end: null,
    },

    outcome: null,

    created_at: new Date().toISOString(),
  };
}

function finalizeCandidateDecision(
  candidateCard,
  decisionPanel,
  learningEvent,
  saved,
) {
  const decision = learningEvent.user_feedback.decision;

  if (decision !== "approve" && decision !== "reject") {
    return;
  }

  // Store temporary browser state on this candidate.
  // The account decision and local receipt have completed before confirmation.
  candidateCard.dataset.reviewStatus = decision;

  // Close the Davey teaching panel.
  decisionPanel.innerHTML = "";
  decisionPanel.hidden = true;

  // Replace the normal decision controls with confirmation.
  const decisionArea = candidateCard.querySelector(".candidate-decision");

  if (!decisionArea) {
    return;
  }

  decisionArea.outerHTML = renderSavedDecision(decision,{localFeedbackStatus:saved.notice.includes('not stored')?'not_stored':'confirmed'});
  closeClipPreview({restoreFocus:false});
  const page=document.querySelector('.clips-page');if(page)page.outerHTML=renderClips();
  return;

}

function switchClipsWorkspace(selectedTab) {
  const clipsPage = selectedTab.closest(".clips-page");

  if (!clipsPage) {
    return;
  }

  const target = selectedTab.dataset.clipsTab;

  clipsPage.querySelectorAll("[data-clips-tab]").forEach((tab) => {
    tab.classList.toggle("active", tab === selectedTab);
  });

  clipsPage.querySelectorAll("[data-clips-panel]").forEach((panel) => {
    panel.hidden = panel.dataset.clipsPanel !== target;
  });
}
