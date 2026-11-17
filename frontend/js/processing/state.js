// ==========================================================
// ClipBot SaaS
// Processing Configuration State
// ==========================================================

const STORAGE_KEY = "clipbot-processing-state";

const DEFAULT_STATE = {
  rules: [
    {
      id: "no-way",
      phrase: "no way",
      source: "Streamer speech",
      priority: "High",
    },
    {
      id: "clip-that",
      phrase: "clip that",
      source: "Chat phrase",
      priority: "High",
    },
    {
      id: "lets-go",
      phrase: "let's go",
      source: "Either",
      priority: "Medium",
    },
    {
      id: "what",
      phrase: "what?!",
      source: "Streamer speech",
      priority: "Medium",
    },
  ],

  candidateSelectivity: 62,
  chatSensitivity: 70,
  keywordImportance: 78,
  minimumConfidence: 75,
  preferredClipLength: "balanced",
};

export function getProcessingState() {
  const saved = sessionStorage.getItem(STORAGE_KEY);

  if (!saved) {
    return structuredClone(DEFAULT_STATE);
  }

  try {
    return {
      ...structuredClone(DEFAULT_STATE),
      ...JSON.parse(saved),
    };
  } catch {
    return structuredClone(DEFAULT_STATE);
  }
}

export function saveProcessingState(state) {
  sessionStorage.setItem(STORAGE_KEY, JSON.stringify(state));
}
