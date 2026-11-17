import {escapeHtml as e} from '../ui-utils.js';
import {selectionOutcome,isSelectionOutcome} from '../selection-outcomes.js';
export function clipWorkflowCounts(jobs=[]){return {collected:jobs.filter(j=>['transcribing','analyzing','review','editing','rendering','ready','publishing','published'].includes(j.stage)||isSelectionOutcome(j)).length,processing:jobs.filter(j=>['transcribing','analyzing','editing','rendering'].includes(j.stage)).length,review:jobs.filter(j=>j.stage==='review').length};}
export function renderWorkflow(steps,items,key='stage',label='Clip workflow'){
 return `<nav class="pipeline-workflow" aria-label="${e(label)}">${steps.map(([id,title,stages])=>`<a class="workflow-step ${items.some(j=>stages.includes(j[key]))?'has-work':''}" href="#workflow-${e(id)}"><span>${e(title)}</span><strong>${items.filter(j=>stages.includes(j[key])).length}</strong></a>`).join('')}</nav>`;
}
export function renderQueueBoard(steps,items,key='stage'){
 return `<div class="pipeline-queue-board">${steps.map(([id,title,stages])=>{const rows=items.filter(j=>stages.includes(j[key]));return `<section class="queue-stage" id="workflow-${e(id)}"><h3>${e(title)} <span>${rows.length}</span></h3><div class="queue-stage-scroll">${rows.map(j=>`<article class="queue-job"><strong>${e(j.source?.login??j.title??(j.clipId?'Clip '+j.clipId.slice(0,6):'Clip'))}</strong><small>${e(j.source?.platform??j.platform??'')} &middot; ${e((key==='stage'&&isSelectionOutcome(j)?selectionOutcome(j.errorCode).title:j[key].replaceAll('_',' ')))}</small>${j.errorCode&&!isSelectionOutcome(j)?`<small>Reason: ${e(j.errorCode.replaceAll('_',' '))}</small>`:''}</article>`).join('')||'<p class="muted">No clips here</p>'}</div></section>`;}).join('')}</div>`;
}
