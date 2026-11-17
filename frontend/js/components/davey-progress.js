// ==========================================================
// ClipBot SaaS
// Davey — Dashboard Progress Component
// ==========================================================
//
// Displays Davey's personalization confidence and trust phase.
//
// Real profile metrics will eventually come from the user's
// local ClipBot worker. This component only displays them.
// ==========================================================

export function renderDaveyProgress(profile) {
  const confidence = profile.confidence;
  const phase = profile.phase;
  const evidence = profile.evidence;

  const phaseDescription = getPhaseDescription(phase.key);
  const nextStep = getNextStep(phase.key);

  return `
        <div class="davey-progress">

            <div class="davey-phase-row">
                <div>
                    <span class="davey-progress-label">
                        Personalization Confidence
                    </span>
                </div>

                <span class="davey-phase-badge">
                    Phase ${phase.number} · ${phase.name}
                </span>
            </div>


            <div class="davey-confidence-row">
                <strong>${confidence}%</strong>
            </div>


            <div class="davey-confidence-track">
                <div
                    class="davey-confidence-fill"
                    style="width: ${confidence}%"
                ></div>
            </div>


            <div class="davey-evidence-row">

                <span>
                    <strong>${evidence.decisions}</strong>
                    decisions
                </span>

                <span>
                    <strong>${evidence.recentAgreement}%</strong>
                    recent agreement
                </span>

            </div>


            <div class="davey-phase-summary">
                <strong>${phase.name}</strong>

                <p>
                    ${phaseDescription}
                </p>
            </div>


            ${
              nextStep
                ? `
                        <div class="davey-next-phase">
                            <span>Next</span>
                            <p>${nextStep}</p>
                        </div>
                    `
                : ""
            }

        </div>
    `;
}

function getPhaseDescription(phaseKey) {
  if (phaseKey === "assisted") {
    return `
            Davey has enough evidence to begin selecting and
            processing clips based on your preferences.
        `;
  }

  if (phaseKey === "autonomous") {
    return `
            Davey's decisions have been validated strongly enough
            to make autonomous capabilities available.
        `;
  }

  return `
        Davey is learning your clipping preferences from your
        reviews, reasoning, and publishing results.
    `;
}

function getNextStep(phaseKey) {
  if (phaseKey === "learning") {
    return `
            Continue reviewing candidates to help Davey qualify
            for Assisted clipping.
        `;
  }

  if (phaseKey === "assisted") {
    return `
            More validated publishing outcomes are needed before
            Autonomous capabilities become available.
        `;
  }

  return null;
}
