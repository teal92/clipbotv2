import {
  getProcessingState,
  saveProcessingState,
} from "../processing/state.js";
import {api,getSessionGeneration,getAccount} from '../service-state.js';

// An active session has no complete Start-to-Stop bundle yet.
export function renderProcessingSessionDownload(sessions=[],running=false){
 const valid=(Array.isArray(sessions)?sessions:[]).filter(s=>s&&/^[a-f0-9]{32}$/.test(s.id??''));
 const stopped=valid.filter(s=>s.state==='stopped'&&Number.isFinite(Date.parse(s.stoppedAt))).sort((a,b)=>(Date.parse(b.startedAt)||0)-(Date.parse(a.startedAt)||0))[0];
 const active=running||valid.some(s=>s.state==='running');
 const guidance='Logs can be downloaded only after the session ends.';
 return `<div class="processing-bundle-action">${!active&&stopped?`<a class="btn" href="/api/logs/sessions/${stopped.id}" download aria-describedby="processing-bundle-hint">Download logs bundle</a>`:`<button class="btn" disabled aria-describedby="processing-bundle-hint">Download logs bundle</button>`}<p id="processing-bundle-hint">${guidance}${!active&&!stopped?' No completed session is available yet.':''}</p></div>`;
}
export async function loadProcessingDiagnostics(root){
 const page=root.matches?.('.processing-page')?root:root.querySelector?.('.processing-page')??root;
 const slot=page?.querySelector?.('[data-processing-session-bundle]');if(!slot)return;
 const generation=getSessionGeneration(),owner=getAccount()?.user?.id;
 const current=()=>generation===getSessionGeneration()&&owner===getAccount()?.user?.id&&page.isConnected!==false;
 try{const result=await api('/api/logs/sessions');if(current())slot.innerHTML=renderProcessingSessionDownload(result.sessions,page.dataset?.sessionRunning==='true');}
 catch{if(current())slot.innerHTML=renderProcessingSessionDownload()+ '<p role="status">Session logs are unavailable. Refresh status to try again.</p>';}
}

// ==========================================================
// ClipBot SaaS
// Processing Controller
// ==========================================================

export function handleProcessingClick(event) {
  const action = event.target.closest("[data-processing-action]");

  if (!action) {
    return;
  }

  const processingPage = action.closest(".processing-page");

  if (!processingPage) {
    return;
  }

  const actionName = action.dataset.processingAction;

  if (actionName === "add-rule") {
    openRuleEditor(processingPage);
    return;
  }

  if (actionName === "edit-rule") {
    openRuleEditor(processingPage, action.closest(".detection-rule"));
    return;
  }

  if (actionName === "delete-rule") {
    const rule = action.closest(".detection-rule");

    if (!rule) {
      return;
    }

    const state = getProcessingState();

    state.rules = state.rules.filter((item) => item.id !== rule.dataset.ruleId);

    saveProcessingState(state);
    rule.remove();

    return;
  }

  if (actionName === "cancel-rule") {
    closeRuleEditor(processingPage);
    return;
  }

  if (actionName === "save-rule") {
    saveRule(processingPage);
  }
}

export function handleProcessingInput(event) {
  const processingPage = event.target.closest(".processing-page");

  if (!processingPage) {
    return;
  }

  if (event.target.matches("[data-processing-range]")) {
    const output = processingPage.querySelector(
      `[data-range-value="${event.target.dataset.processingRange}"]`,
    );

    if (output) {
      output.textContent = `${event.target.value}%`;
    }

    const state = getProcessingState();

    state[event.target.dataset.processingRange] = Number(event.target.value);

    saveProcessingState(state);
  }

  if (event.target.matches("[data-min-confidence]")) {
    const value = Number(event.target.value);

    if (value < 0) {
      event.target.value = 0;
    }

    if (value > 100) {
      event.target.value = 100;
    }

    const state = getProcessingState();

    state.minimumConfidence = Number(event.target.value);

    saveProcessingState(state);
  }

  if (event.target.matches("[data-preferred-length]")) {
    const state = getProcessingState();

    state.preferredClipLength = event.target.value;

    saveProcessingState(state);
  }
}

function openRuleEditor(processingPage, rule = null) {
  const editor = processingPage.querySelector("[data-rule-editor]");

  if (!editor) {
    return;
  }

  const phraseInput = editor.querySelector("[data-rule-phrase]");

  const sourceInput = editor.querySelector("[data-rule-source]");

  const priorityInput = editor.querySelector("[data-rule-priority]");

  editor.dataset.editingRule = "";

  if (rule) {
    phraseInput.value = rule.dataset.rulePhrase || "";

    sourceInput.value = rule.dataset.ruleSource || "Either";

    priorityInput.value = rule.dataset.rulePriority || "Medium";

    editor.dataset.editingRule = rule.dataset.ruleId || "";
  } else {
    phraseInput.value = "";
    sourceInput.value = "Either";
    priorityInput.value = "Medium";
  }

  editor.hidden = false;
  phraseInput.focus();
}

function closeRuleEditor(processingPage) {
  const editor = processingPage.querySelector("[data-rule-editor]");

  if (!editor) {
    return;
  }

  editor.hidden = true;
  editor.dataset.editingRule = "";
}

function saveRule(processingPage) {
  const editor = processingPage.querySelector("[data-rule-editor]");

  const rules = processingPage.querySelector(".detection-rules");

  if (!editor || !rules) {
    return;
  }

  const phrase = editor.querySelector("[data-rule-phrase]").value.trim();

  const source = editor.querySelector("[data-rule-source]").value;

  const priority = editor.querySelector("[data-rule-priority]").value;

  if (!phrase) {
    return;
  }

  const editingId = editor.dataset.editingRule;
  const state = getProcessingState();

  if (editingId) {
    const existingRule = rules.querySelector(`[data-rule-id="${editingId}"]`);

    if (existingRule) {
      updateRule(existingRule, phrase, source, priority);
    }
    const savedRule = state.rules.find((item) => item.id === editingId);

    if (savedRule) {
      savedRule.phrase = phrase;
      savedRule.source = source;
      savedRule.priority = priority;
    }
  } else {
    const rule = document.createElement("div");

    rule.className = "detection-rule";

    const newRule = {
      id: `rule-${Date.now()}`,
      phrase,
      source,
      priority,
    };

    rule.dataset.ruleId = newRule.id;

    state.rules.push(newRule);

    rules.appendChild(rule);

    updateRule(rule, phrase, source, priority);
  }

  saveProcessingState(state);
  closeRuleEditor(processingPage);
}

function updateRule(rule, phrase, source, priority) {
  rule.dataset.rulePhrase = phrase;
  rule.dataset.ruleSource = source;
  rule.dataset.rulePriority = priority;

  rule.innerHTML = `
    <div class="rule-main">
      <strong>“${escapeHtml(phrase)}”</strong>
      <span>${escapeHtml(source)}</span>
    </div>

    <span class="rule-priority">
      ${escapeHtml(priority)}
    </span>

    <button
      class="rule-action"
      data-processing-action="edit-rule"
    >
      Edit
    </button>

    <button
      class="rule-action"
      data-processing-action="delete-rule"
      title="Remove rule"
    >
      ×
    </button>
  `;
}

function escapeHtml(value) {
  const element = document.createElement("div");
  element.textContent = value;
  return element.innerHTML;
}
