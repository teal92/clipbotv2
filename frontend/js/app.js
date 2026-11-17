import {connectCustomerAccessControls} from './customer-access.js';
import {startOnboarding,stopOnboarding,connectOnboardingControls} from './controllers/onboarding-controller.js';
import {connectCustomBillingControls} from './controllers/custom-billing-controller.js';
import {startLogs} from './controllers/workspace-controller.js';
import {handleTriggerClick,handleTriggerSubmit} from './controllers/trigger-controller.js';
import {startCompanionControls,stopCompanionControls,handleCompanionClick} from './controllers/companion-controller.js';
import {startScouts,stopScouts,handleScoutsClick,handleScoutsSubmit} from './controllers/scouts-controller.js';
import {startPipeline,stopPipeline,handlePipelineClick,handlePipelineSubmit,handlePipelineChange} from './controllers/pipeline-controller.js';
import {renderConnections} from './views/connections.js';
import {connectConnectionControls,loadConnections} from './controllers/connections-controller.js';
import {startPresence,stopPresence} from './controllers/presence-controller.js';
import {connectAccountProfileControls,selectAccountSection} from './controllers/account-profile-controller.js';
import {renderReports} from './views/reports.js';
import {renderSignupReadiness} from './views/auth.js';
import {signupPending,api,refreshWorkspace} from './service-state.js';
import {renderAuth} from './views/auth.js';
import {renderAccount} from './views/account.js';
import {renderUsage} from './views/usage.js';
import {loadSession,getAccount,resetSession} from './service-state.js';
import {connectAccountControls} from './controllers/account-controller.js';
// Individual ClipBot views.
// Each view owns its own interface while app.js handles routing.
import { renderDashboard } from "./views/dashboard.js";
import { renderStreamers } from "./views/streamers.js";
import { renderClips } from "./views/clips.js";
import { handleClipsClick } from "./controllers/clips-controller.js";
import { renderProcessing } from "./views/processing.js";
import {startDashboardMetrics,stopDashboardMetrics,handleDashboardClick,handleDashboardChange} from './controllers/dashboard-controller.js';
import {handleClipPreviewClick,closeClipPreview} from './controllers/clip-preview-controller.js';
import { renderPublishing } from "./views/publishing.js";
import {DAVEY_PHASES} from './views/davey.js';
import { renderDavey } from "./views/davey.js";
import { renderLogs } from "./views/logs.js";

import { handleWorkspaceClick, handleWorkspaceSubmit, handleWorkspaceInput, stopWorkspaceActivity } from "./controllers/workspace-controller.js";
import { handlePublishingSubmit } from "./controllers/publishing-controller.js";

import {
  loadProcessingDiagnostics,
  handleProcessingClick,
  handleProcessingInput,
} from "./controllers/processing-controller.js";

// ==========================================================
// ClipBot SaaS
// Main frontend controller
// ==========================================================

// Grab the parts of the page that our controller needs.
const pageTitle = document.getElementById("page-title");
const pageSubtitle = document.getElementById("page-subtitle");
const appContent = document.getElementById("app-content");

const navItems = document.querySelectorAll(".nav-item");

// Information associated with each ClipBot view.
//
// Later, the actual page contents will live in separate files under
// js/views/. For now we're proving that the application shell works.
let currentView='dashboard';
const views = {
 scouting:{title:'Scouting',subtitle:'Category coverage, scout activity and live streams'},
 connections:{title:'Connect Accounts',subtitle:'Streaming, social publishing and service connections'},
 reports:{title:'Reports',subtitle:'Report bugs, suggest improvements and share feedback'},
 account:{title:'Account',subtitle:'Identity, plan coverage and billing'},
 usage:{title:'Usage',subtitle:'Davey tokens and plan allowances'},
  dashboard: {
    title: "Dashboard",
    subtitle: "ClipBot control center",
  },

  streamers: {
    title: "Streamers",
    subtitle: "Scout settings, streamer priorities and monitoring controls",
  },

  clips: {
    title: "Clips",
    subtitle: "Review clips discovered by ClipBot",
  },

  processing: {
    title: "Processing",
    subtitle: "View the processing tab and see under the hood",
  },

  publishing: {
    title: "Publishing",
    subtitle: "Manage connected platforms and publishing",
  },

  davey: {
    title: "Davey",
    subtitle: "Your personal ClipBot intelligence",
  },

  logs: {
    title: "Logs",
    subtitle: "ClipBot activity and worker connection",
  },

  settings: {
    title: "Settings",
    subtitle: "Configure ClipBot",
  },
};

// ----------------------------------------------------------
// Render a view
// ----------------------------------------------------------

function renderView(viewName) {
  if(viewName==='settings')viewName='account';
  if(globalThis.window?.location&&!getAccount()){showAuth(renderAuth());return;}
  currentView=viewName;
  const view = views[viewName];

  // Ignore invalid view names instead of crashing the application.
  if (!view) {
    console.warn(`Unknown ClipBot view: ${viewName}`);
    return;
  }

  stopDashboardMetrics();closeClipPreview({restoreFocus:false});
  stopWorkspaceActivity();
  stopScouts();stopPipeline();

  // Update the page header.
  pageTitle.textContent = view.title;
  pageSubtitle.textContent = view.subtitle;

  if (viewName === 'connections') {
    appContent.innerHTML=renderConnections();
    if(globalThis.window?.location)loadConnections(appContent,()=>{resetSession();showAuth(renderAuth());});
  } else if (viewName === 'reports') {
    appContent.innerHTML=renderReports();
  } else if (viewName === 'account') {
    appContent.innerHTML=renderAccount();
  } else if (viewName === 'usage') {
    appContent.innerHTML=renderUsage();
  } else if (viewName === "dashboard") {
    appContent.innerHTML = renderDashboard();
    if(globalThis.window?.location)startDashboardMetrics(appContent,()=>showAuth(renderAuth()));
  } else if (["streamers","scouting"].includes(viewName)) {
    appContent.innerHTML = renderStreamers(undefined,[],[],null,{},viewName);
    if(globalThis.window?.location)startScouts(appContent,()=>showAuth(renderAuth()));
  } else if (viewName === "clips") {
    appContent.innerHTML = renderClips();
  } else if (viewName === "processing") {
    appContent.innerHTML = renderProcessing();
    if(globalThis.window?.location)loadProcessingDiagnostics(appContent);
  } else if (viewName === "publishing") {
    appContent.innerHTML = renderPublishing();
  } else if (viewName === "davey") {
    appContent.innerHTML = renderDavey();
  } else if (viewName === "logs") {
    appContent.innerHTML = renderLogs();
    startLogs(appContent);
  } else {
    appContent.innerHTML = `
            <div class="welcome-card">
                <p class="eyebrow">CLIPBOT SAAS</p>
                <h2>${view.title}</h2>
                <p>The ${view.title} workspace will be built here.</p>
            </div>
        `;
  }

  if(globalThis.window?.location&&['dashboard','clips','processing','publishing'].includes(viewName))startPipeline(appContent,()=>showAuth(renderAuth()));

  // Remove the active state from every navigation button.
  navItems.forEach((item) => {
    item.classList.remove("active");
  });

  // Highlight the selected navigation button.
  const activeItem = document.querySelector(
    `.nav-item[data-view="${viewName}"]`,
  );
  activeItem?.classList.add("active");
  globalThis.window?.scrollTo(0, 0);
  document.querySelector('.main-area')?.scrollTo?.(0,0);
}

// ----------------------------------------------------------
// Navigation events
// ----------------------------------------------------------

navItems.forEach((item) => {
  item.addEventListener("click", () => {
    const viewName = item.dataset.view;

    renderView(viewName);
  });
});

document.addEventListener("click",event=>{
 const phase=event.target.closest('[data-davey-phase]'),close=event.target.closest('[data-davey-phase-close]'),dialog=document.querySelector('[data-davey-phase-dialog]');
 if(close){dialog?.close();return;}
 const value=phase&&DAVEY_PHASES[Number(phase.dataset.daveyPhase)];if(!value||!dialog)return;
 dialog.querySelector('[data-phase-title]').textContent=value.name;dialog.querySelector('[data-phase-description]').textContent=value.description;dialog.showModal();
});
document.addEventListener("click", handleDashboardClick);
document.addEventListener("change", handleDashboardChange);
document.addEventListener("click", handleClipPreviewClick);
document.addEventListener("click", handleClipsClick);
document.addEventListener("click",handleScoutsClick);
document.addEventListener("click",handleTriggerClick);
document.addEventListener("submit",handleTriggerSubmit);
document.addEventListener("submit",handleScoutsSubmit);
document.addEventListener("click",handlePipelineClick);
document.addEventListener("submit",handlePipelineSubmit);
document.addEventListener("change",handlePipelineChange);

document.addEventListener("click", handleProcessingClick);

document.addEventListener("input", handleProcessingInput);
document.addEventListener("submit", handlePublishingSubmit);
document.addEventListener("click", handleCompanionClick);
document.addEventListener("click", handleWorkspaceClick);
document.addEventListener("submit", handleWorkspaceSubmit);
document.addEventListener("input", handleWorkspaceInput);
document.addEventListener("change", handleWorkspaceInput);

// ----------------------------------------------------------
// Initial application state
// ----------------------------------------------------------

function showAuth(html){
 stopOnboarding();
 document.querySelector('[data-custom-checkout-dialog]')?.close();
 stopDashboardMetrics();closeClipPreview({restoreFocus:false});
 stopCompanionControls();stopWorkspaceActivity();stopPresence();stopScouts();stopPipeline();
 const shell=document.querySelector('.app-shell'),auth=document.getElementById('auth-root');
 if(shell)shell.hidden=true;
 if(auth){auth.hidden=false;auth.innerHTML=html;}
}
function showWorkspace(){
 if(signupPending()){showAuth(renderSignupReadiness(getAccount()));return;}
 const shell=document.querySelector('.app-shell'),auth=document.getElementById('auth-root');
 if(shell)shell.hidden=false;
 if(auth){auth.hidden=true;auth.innerHTML='';}
 startPresence();startCompanionControls(document,()=>showAuth(renderAuth()));
 const requestedView=new URLSearchParams(globalThis.window?.location?.search??'').get('view');
 renderView(['account','settings','connections'].includes(requestedView)?requestedView:'dashboard');
 startOnboarding();
}
connectOnboardingControls(renderView);
connectCustomBillingControls();
connectConnectionControls({showAuth,authHtml:renderAuth});
connectAccountControls({showWorkspace,showAuth,refresh:()=>renderView(currentView)});
connectCustomerAccessControls({refresh:()=>signupPending()?showAuth(renderSignupReadiness(getAccount())):showWorkspace()});
document.addEventListener('click',async event=>{const button=event.target.closest('[data-signup-check]');if(!button)return;button.disabled=true;try{await refreshWorkspace();if(signupPending()){document.querySelector('[data-signup-status]').textContent='Email verification and current policies are still required.';}else showWorkspace();}catch(error){document.querySelector('[data-signup-status]').textContent=error.message;}finally{button.disabled=false;}});
connectAccountProfileControls({showAuth,refresh:()=>renderView(currentView)});
if(globalThis.window?.location){
 showAuth('<p class="loading-message">Opening ClipBot…</p>');
 loadSession().then(connected=>connected?showWorkspace():showAuth(renderAuth())).catch(()=>{
  showAuth(renderAuth());
  const output=document.querySelector('[data-auth-status]');
  if(output)output.textContent='Cannot reach the account service. Start the ClipBot backend, then reload.';
 });
}else renderView('dashboard');

// ----------------------------------------------------------
// Dashboard / page action navigation
// ----------------------------------------------------------
//
// Some buttons are created dynamically when a view renders,
// so we listen on the document instead of attaching listeners
// individually every time a page is created.

document.addEventListener("click", (event) => {
 const summary=event.target.closest?.(".scout-preview-grid summary");if(summary&&!summary.parentElement.open){const card=summary.closest("[data-preview-key]");card.style.minHeight=card.getBoundingClientRect().height+"px";}
  const action = event.target.closest("[data-open-view]");

  // Ignore clicks that are not navigation actions.
  if (!action) {
    return;
  }

  const viewName = action.dataset.openView;

  renderView(viewName);
});





document.addEventListener('toggle',event=>{if(event.target.matches?.('.scout-preview-grid details')){const frame=event.target.querySelector('[data-scout-preview-src]');const card=event.target.closest('[data-preview-key]');card.classList.toggle('scout-live-expanded',event.target.open);const media=card.querySelector('.scout-snapshot');card.style.setProperty('--scout-media-top',(media.getBoundingClientRect().top-card.getBoundingClientRect().top)+'px');card.style.setProperty('--scout-media-left',(media.getBoundingClientRect().left-card.getBoundingClientRect().left)+'px');card.style.removeProperty('min-height');if(!event.target.open)card.style.removeProperty('min-height');card.style.setProperty('--scout-live-scale',String(event.target.clientWidth/640));event.target.querySelector('summary').textContent=event.target.open?'Back to snapshots':'Go live';card.style.setProperty('--scout-summary-height',event.target.querySelector('summary').getBoundingClientRect().height+'px');if(event.target.open&&frame&&!frame.getAttribute('src'))frame.setAttribute('src',frame.dataset.scoutPreviewSrc);else if(!event.target.open&&frame)frame.removeAttribute('src');}},true);

globalThis.window?.addEventListener?.('resize',()=>{for(const detail of document.querySelectorAll('.scout-preview-grid details[open]')){const card=detail.closest('[data-preview-key]'),media=card.querySelector('.scout-snapshot');card.style.setProperty('--scout-live-scale',String(detail.clientWidth/640));card.style.setProperty('--scout-media-top',(media.getBoundingClientRect().top-card.getBoundingClientRect().top)+'px');card.style.setProperty('--scout-media-left',(media.getBoundingClientRect().left-card.getBoundingClientRect().left)+'px');}});
