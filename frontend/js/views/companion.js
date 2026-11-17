import {renderPatchNotes} from '../release-notes.js';
import {SETUP_GUIDE} from '../onboarding.js';

import {escapeHtml as e} from '../ui-utils.js';
import {COMPANION_PLATFORMS,platformLabel,downloadUrl} from '../companion-platform.js';

const hints={trigger_settings_unavailable:'Scouting is paused because clip trigger settings could not load. Refresh or reconnect the companion.',tools_missing:'Reinstall the companion to repair local processing.',analysis_paused:'Davey analysis is paused. Check your plan allowance and Streamers preferences.',beta_required:'Acknowledge feedback privacy in Streamers.',coverage_unavailable:'Active plan coverage is required.'};

const labels={offline:'Offline',ready:'Ready',starting:'Starting',running:'Running',stopping:'Stopping',attention:'Needs attention'};

function installerDownloadControl(d){

 const os=d.target?.startsWith('macos-')?'macOS':d.target==='linux-x86_64'?'Linux':'Windows';
 const publisherNotice=os==='macOS'?'This beta has no verified Apple Developer ID and is not notarized by Apple.':'This installer is not code-signed.';
 const desktopNotice=d.desktopAcceptancePending?'<p>Experimental public beta: automated package checks passed. Real desktop installation and pairing have not yet been verified. Please report setup problems through Reports and Feedback.</p>':'';
 const warning=d.signed?'':`<div class="notice" role="note"><strong>Unsigned beta</strong><p>${publisherNotice} ${os} cannot verify YOUR COMPANY NAME as the publisher and may display a security warning. Download only from ClipBot and install only if you choose to trust this beta release. Do not disable your antivirus or operating-system security protections.</p>${desktopNotice}</div>`;

 return warning+'<div class="companion-actions">'+(d.requiresBetaAcceptance?'<button class="btn approve" data-companion-action="accept-beta">I understand - enable unsigned beta download</button>':`<a class="btn approve" href="${e(downloadUrl(d))}" rel="noopener noreferrer" download>Download for ${e(platformLabel(d.target??'windows-x86_64'))}</a>`)+'</div>';

}

export function companionHint(s){return s.state==='attention'?(hints[s.errorCode]??'Check the companion and your account prerequisites.'):'';}

export function renderCompanionStatus(s){return `<button class="btn companion-check" data-companion-action="check">Check companion</button><a class="btn setup-guide" href="${SETUP_GUIDE}" target="_blank" rel="noopener noreferrer">Click Here for initial ClipBot setup</a><button class="clipbot-start" data-companion-action="start" ${s.requestedRunning?'disabled':''}>Start ClipBot</button><button class="clipbot-stop" data-companion-action="stop" ${!s.requestedRunning&&s.state!=='stopping'?'disabled':''}>Stop ClipBot</button><span class="companion-state" data-state="${e(s.state)}" title="${e(hints[s.errorCode]??'')}"><span class="status-dot"></span>${e(s.state==='attention'?({analysis_paused:'Enable Davey',beta_required:'Review feedback privacy',coverage_unavailable:'Check plan',tools_missing:'Repair companion'}[s.errorCode]??'Check Logs'):labels[s.state]??'Offline')}</span>`;}

export function renderCompanionPairing(code){
 return `<section class="companion-pairing"><p>Connect this computer to your signed-in ClipBot account.</p><div class="companion-actions"><a class="btn approve" href="clipbot-companion://pair?code=${encodeURIComponent(code)}">Open ClipBot Companion</a></div><div data-pairing-copy-slot></div><p class="muted">For manual pairing, open the companion tray menu, choose Connection status and paste the code. Once connected, close this window and press Start ClipBot.</p></section>`;
}

export function renderCompanionSetup(d,{reason='setup',version=null}={}){
 d={...d,available:!!(d.available&&downloadUrl(d))};
 const choices='<fieldset class="companion-platforms"><legend>Choose your computer</legend><div class="companion-actions">'+Object.entries(COMPANION_PLATFORMS).map(([target,label])=>`<button class="btn" data-companion-action="choose-platform" data-companion-target="${target}" aria-pressed="${d.target===target}">${e(label)}</button>`).join('')+'</div><p class="muted">On a Mac, open Apple menu → About This Mac. “Chip” means Apple Silicon; “Processor: Intel” means Intel.</p></fieldset>';
 const title={check:'ClipBot up to date',update:d.releaseKind==='patch'?'ClipBot Companion beta patch update':'Update ClipBot Companion',repair:'Repair ClipBot Companion',connect:'Connect your installed companion',setup:'Set up ClipBot on this computer'}[reason];
 const notice=reason==='update'?`Your companion reports version ${e(version)}. ${d.releaseKind==='patch'?'Beta patch':'Version'} ${e(d.version)} is available. Stop ClipBot, close the companion, then run this update. Your pairing and local data stay in place. Return here and check the companion before pressing Start.`:reason==='connect'?'The website did not receive a recent companion check-in. If it is already installed, open it from your system tray or Start menu and wait for Ready. You only need the download below if it is not installed.':'';
 return `<h2 id="companion-title">${title}</h2>${notice?`<p role="status">${notice}</p>`:''}${reason==='update'?renderPatchNotes(d.version):''}<p>The companion monitors streams and processes clips on this computer. It runs in the system tray or menu bar; your computer must stay on.</p>${choices}<div class="companion-steps"><section class="companion-step"><h3><span aria-hidden="true">1</span> Download &amp; install</h3><p>Download the installer, open it and finish setup. Already installed? Continue to step 2.</p>${d.available?`${installerDownloadControl(d)}<p class="companion-version">Version ${e(d.version)} &middot; ${d.signed?'Signed installer':'Unsigned beta installer'}${d.minimumOS?` &middot; Requires ${e(d.minimumOS)} or newer`:''}</p><details class="companion-checksum"><summary>Download checksum</summary><code>${e(d.sha256)}</code></details>`:`<div class="companion-actions"><button class="btn" disabled>${d.ambiguousArchitecture?'Choose your Mac processor above':`Download for ${e(platformLabel(d.target??'windows-x86_64'))}`}</button></div><p>${d.ambiguousArchitecture?'Select Apple Silicon or Intel to see the matching package.':'The download for this computer is being prepared. Try again shortly.'}</p>`}</section><section class="companion-step"><h3><span aria-hidden="true">2</span> Connect companion</h3><p>After installation, connect this computer to your account. Updates keep your existing pairing.</p><div class="companion-actions"><button class="btn" data-companion-action="pair">Connect installed companion</button></div><div data-companion-pair></div></section></div><p data-companion-message role="status"></p><footer class="companion-dialog-footer"><button class="btn" data-companion-action="close">${reason==='update'?'Remind me next visit':'Close'}</button></footer>`;
}
