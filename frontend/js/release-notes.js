import {escapeHtml as e} from './ui-utils.js';

// Static release history: no remote HTML or customer-supplied content is rendered.
export const releaseNotes={
 '0.3.0-beta.1':[
  ['Apple Silicon Mac beta','An experimental companion download for M-series Macs running macOS 14 or newer. Choose Apple Silicon in companion setup. Intel Mac and Linux downloads are still being checked.'],
  ['Private account pairing','Connect the Mac companion through your signed-in ClipBot account. Pairing credentials are stored in macOS Keychain. Your plan and usage limits still apply.'],
  ['What has been checked','Automated package checks passed for local transcription, clip rendering, processor compatibility and secure media connections. Real desktop installation and pairing still need beta feedback.'],
  ['Before installing','This beta has no verified Apple Developer ID and is not notarized by Apple. Read the download notice before installing. Windows remains on companion 0.2.10.']
 ],
 '0.2.10':[
  ['Your favorites, ready when live','Add favorite streamers and categories separately. Scouts prioritize them when available, within your scout slots.'],
  ['A cleaner scouting view','Favorites use gold text. Other scouts stay white, with consistent borders and backgrounds. “Forced” selections are now called favorites.'],
  ['Clips when the moment happens','Your enabled audio, speech and chat signals trigger clips using your before/after timing and cooldown. Clip now still works manually.'],
  ['No reviews for quiet footage','A short temporary buffer keeps the moments before a trigger. Buffering alone uses no AI reviews. Missing trigger settings pause scouting.'],
  ['Keep watching while favorites wait','Favorite categories no longer block discovery of other eligible streams. Your other saved category filters still apply.'],
  ['Easier setup and pairing','Clearer Download, Connect and Open Companion controls, plus Copy code with confirmation. Unfinished favorite entries survive page updates.'],
  ['Patch notes whenever you need them','Open Account → Patch notes to read this update and previous release notes at any time.']
 ],
 '0.2.9':[
  ['Clip lengths','More reliable clip duration selection and fractional timestamps. Windows too short for your settings skip paid analysis.'],
  ['Analysis requests','Routine stream discovery no longer consumes the analysis request allowance.'],
  ['Kick chat','Accepts Kick’s current token lifetime while keeping the local token cache bounded.'],
  ['Clearer diagnostics','More specific processing errors, with private provider responses excluded.'],
  ['Bulk phrases','Paste comma-separated phrases in Streamers, then choose each row’s input and tolerance.'],
  ['Security checks','Added SQL injection attack tests. Existing account isolation, spending caps and unsigned-beta protections remain active.']
 ]
};

export function renderPatchNotes(version){
 const notes=Object.hasOwn(releaseNotes,version)?releaseNotes[version]:[];
 return `<section class="companion-patch-notes" aria-label="Patch notes ${e(version)}"><h3>What’s new in ${e(version)}</h3>${notes.length?`<ul>${notes.map(([title,detail])=>`<li><strong>${e(title)}</strong><p>${e(detail)}</p></li>`).join('')}</ul>`:'<p>No additional notes were published for this version.</p>'}<p class="muted">Your existing plan limits and spending safeguards stay in place.</p></section>`;
}

export function renderPatchHistory(){
 return `<section class="workspace-card"><h3>Patch notes</h3><p>Read what changed in each ClipBot beta update. Companion fixes apply after you install the matching update.</p>${Object.keys(releaseNotes).map(renderPatchNotes).join('')}</section>`;
}
