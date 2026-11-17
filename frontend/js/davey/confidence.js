// ==========================================================
// ClipBot SaaS
// Davey — Personalization Confidence
// ==========================================================
//
// Prototype confidence / trust-phase model.
//
// IMPORTANT:
// This is currently frontend prototype logic.
// Davey's authoritative profile will eventually live with
// the user's local ClipBot worker.
//
// Confidence = how well Davey understands the user.
// Phase      = what the evidence says Davey is ready to do.
// Permission = what the user actually allows Davey to do.
// ==========================================================

const MAX_CONFIDENCE = 97;

// Initial product thresholds.
// These are intentionally configurable because real ClipBot
// usage data should eventually determine better thresholds.
const PHASE_THRESHOLDS = {
  assisted: {
    minimumDecisions: 125,
    minimumAgreement: 85,
    minimumDiversity: 60,
  },

  autonomous: {
    minimumDecisions: 275,
    minimumAgreement: 90,
    minimumDiversity: 75,
    minimumValidatedOutcomes: 75,
  },
};

export function calculateDaveyProfile(metrics = {}) {
  const decisions = Number(metrics.decisions || 0);

  const recentAgreement = clamp(Number(metrics.recentAgreement || 0), 0, 100);

  const diversity = clamp(Number(metrics.diversity || 0), 0, 100);

  const validatedOutcomes = Math.max(0, Number(metrics.validatedOutcomes || 0));

  // ------------------------------------------------------
  // 1. Evidence score
  //
  // Decision volume has diminishing returns.
  // Reaching 300 decisions provides the full volume score.
  // ------------------------------------------------------

  const evidenceScore = clamp((decisions / 300) * 100, 0, 100);

  // ------------------------------------------------------
  // 2. Outcome validation
  //
  // Publishing results tell Davey whether predictions and
  // user preferences actually worked with the audience.
  // ------------------------------------------------------

  const outcomeScore = clamp((validatedOutcomes / 75) * 100, 0, 100);

  // ------------------------------------------------------
  // 3. Personalization confidence
  //
  // These are initial product weights, NOT scientifically
  // calibrated values. Real usage data should tune them.
  // ------------------------------------------------------

  const rawConfidence =
    evidenceScore * 0.4 +
    recentAgreement * 0.3 +
    diversity * 0.15 +
    outcomeScore * 0.15;

  // Davey should never communicate absolute certainty.
  const confidence = Math.min(MAX_CONFIDENCE, Math.round(rawConfidence));

  // ------------------------------------------------------
  // 4. Trust phase
  //
  // IMPORTANT:
  // More decisions alone cannot advance Davey.
  // Agreement/diversity/outcomes must also qualify.
  // ------------------------------------------------------

  let phase = {
    number: 1,
    key: "learning",
    name: "Learning",
  };

  const assistedReady =
    decisions >= PHASE_THRESHOLDS.assisted.minimumDecisions &&
    recentAgreement >= PHASE_THRESHOLDS.assisted.minimumAgreement &&
    diversity >= PHASE_THRESHOLDS.assisted.minimumDiversity;

  const autonomousReady =
    decisions >= PHASE_THRESHOLDS.autonomous.minimumDecisions &&
    recentAgreement >= PHASE_THRESHOLDS.autonomous.minimumAgreement &&
    diversity >= PHASE_THRESHOLDS.autonomous.minimumDiversity &&
    validatedOutcomes >= PHASE_THRESHOLDS.autonomous.minimumValidatedOutcomes;

  if (assistedReady) {
    phase = {
      number: 2,
      key: "assisted",
      name: "Assisted",
    };
  }

  if (autonomousReady) {
    phase = {
      number: 3,
      key: "autonomous",
      name: "Autonomous",
    };
  }

  return {
    confidence,

    phase,

    evidence: {
      decisions,
      recentAgreement,
      diversity,
      validatedOutcomes,
    },

    readiness: {
      assisted: assistedReady,
      autonomous: autonomousReady,
    },
  };
}

function clamp(value, min, max) {
  return Math.min(Math.max(value, min), max);
}
