# Website Controls and Background Companion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Preserve the user's previously selected native execution method; perform one independent whole-branch review at the end.

**Goal:** A Windows customer installs once, then starts/stops ClipBot from the website while its companion stays in the tray.
**Architecture:** Extend the existing account-owned scout configuration with revision-bound companion acknowledgment. Package the existing local worker into a per-user Windows tray application and installer. The website guides installation/pairing and consumes authenticated status; it never launches arbitrary processes or assumes a browser tab means monitoring is running.
**Tech Stack:** Existing FastAPI/SQLite, Vanilla JS/CSS, Python worker; pystray/Pillow for tray UI, PyInstaller for a windowless runtime, Inno Setup for a per-user installer. Dependencies/compiler come from official registries/vendor sources; no paid purchase or signing identity is assumed.
**Spec:** docs/superpowers/specs/2026-10-11-companion-controls-design.md (approved).

## Global constraints
- Windows initial target; do not advertise unavailable Mac/Linux support.
- Local media and existing account/plan/beta/budget/publication protections remain in force.
- Default at most two capture slots within plan and hardware allowance.
- No command-line customer setup, console window, fake installer link, or bundled server secrets.
- Stop cancels scouting, preserves completed clips and keeps the companion alive; no duplicate uncertain uploads.
- Installation offers explicit, reversible Start with Windows consent.
- Private repository stays private. Public Download remains unavailable until a real approved public binary URL/version/checksum exists.
- No signed-publisher claim unless a signing identity is actually available.

## Review focus
1. A stale acknowledgment must not turn a newer Stop into Running (Task 1).
2. Multiple browser tabs or accounts must not transfer control or restore old state (Tasks 1/2).
3. Duplicate executable launches/app links must not create duplicate workers or invoke commands (Task 4).
4. Sleep/network loss and cancelled work must not cause unexpected restart or repeated paid/upload calls (Task 3).
5. Frozen installation must work without the developer checkout, Python, FFmpeg on PATH, credentials, or model cache (Task 5).

### Task 1: Account-owned control and acknowledged status
**Files:** Create server/companion.py, server/companion_api.py, tests/test_companion.py; modify server/app.py, server/scouts.py, server/store.py, server/worker_api.py.
**Interfaces:** GET /api/companion/status returns state, requestedRunning, revision, lastSeen, activeScouts, readiness/error code, and safe download metadata. POST /api/companion/control accepts only {running:bool} using current session+CSRF. Device heartbeat accepts a strict bounded report: ready, monitoring, acknowledgedRevision, hardwareSlots, activeScouts, and allowlisted errorCode. It cannot change website intent.
- [ ] Write tests for tenant/CSRF rejection, preserving selections on Start/Stop, default two slots clamped to coverage/hardware, no healthy worker Start denial, offline Stop success, and unchanged plan/budget enforcement.
- [ ] Write state tests asserting stale heartbeat -> Offline; healthy idle -> Ready; unmatched running request -> Starting; matching running acknowledgment -> Running; unmatched stop -> Stopping; matching idle acknowledgment -> Ready; blocked readiness -> Needs attention. Use a 90-second heartbeat expiry to match the existing device boundary.
- [ ] Run .venv/Scripts/python.exe -m pytest tests/test_companion.py -q and verify intended failures.
- [ ] Implement CompanionStore.status(uid)->dict, control(uid,running)->dict, and report(device_token,report)->dict. Store acknowledgment against the device token hash and configuration revision; validate identity/expiry atomically. Preserve existing legacy heartbeat compatibility without granting legacy workers a healthy running acknowledgment.
- [ ] Add guarded installer metadata from CLIPBOT_COMPANION_DOWNLOAD_URL, CLIPBOT_COMPANION_VERSION, CLIPBOT_COMPANION_SHA256. Accept HTTPS only and no credentials; absent/incomplete metadata returns unavailable, never a guessed URL.
- [ ] Run focused tests plus existing worker/scout tests; commit after green.

### Task 2: Website header controls and first-use setup
**Files:** Create frontend/js/controllers/companion-controller.js, frontend/js/views/companion.js, tests/companion.test.mjs; modify frontend/index.html, frontend/css/clipbot.css, frontend/js/app.js, frontend/js/views/connections.js, tests/navigation.test.mjs.
**Interfaces:** Consume Task 1 status/control. Export renderCompanionStatus(status), renderCompanionSetup(download), startCompanionControls(root,onExpired), stopCompanionControls(), and delegated control handlers. Existing account-generation checks remain authoritative.
- [ ] Write tests asserting green Start/red Stop precede status/Account, Offline Start opens setup, Stop stays available for outstanding requests, Starting never says Running, unknown states fail closed, and platform/error text is escaped.
- [ ] Write tests for absent download metadata, truthful unsigned beta copy, safe HTTPS links, modal cancel/focus behavior, session expiry/manual refresh, and stale responses after account switch.
- [ ] Run node --test tests/companion.test.mjs; verify failures.
- [ ] Implement responsive header controls and a modal with the spec's exact companion explanation, Download for Windows, Connect installed companion, and Cancel. Use an explicit click to create the existing one-time pairing code and open a tightly constructed clipbot-companion://pair?code=... link. Provide the manual code fallback without requesting social keys.
- [ ] Poll sequentially while signed in and stop on logout/expiry; integrate refresh across views. Existing Streamers start/stop uses the same service control so the header reflects it.
- [ ] Run all JS checks, then browser desktop/mobile checks with screenshots. Commit after green.

### Task 3: Worker lifecycle and run acknowledgment
**Files:** Create worker/lifecycle.py, tests/test_companion_lifecycle.py; modify worker/local_app.py, worker/runtime.py, worker/client.py, worker/processor.py, worker/prerequisites.py.
**Interfaces:** CompanionLifecycle.start(), stop_monitoring(), status()->dict, shutdown(). WorkerClient.heartbeat(report=None) sends Task 1 report. Runtime reports acknowledgment only after applying current configuration/cancellation, not before.
- [ ] Write tests for Start/Stop with two active captures, retained completed review clips, worker alive while stopped, readiness errors, stale configuration revisions, and revocation clearing previews/halting all components.
- [ ] Write forced-interleaving tests for Stop during discovery, network outage during analysis/upload, and subsequent reconnect. Assert no retry of uncertain paid/upload work and no captured window after revoked access.
- [ ] Run focused tests and verify intended failures.
- [ ] Extract lifecycle ownership from local_app into the lifecycle module. Persist identity outside bundled program files; create job/model paths under per-user LocalAppData/ClipBotCompanion. Use readiness based on actual tools/model/controller health rather than paired token alone.
- [ ] Add bounded network backoff (5,10,20,30 seconds maximum) for transient service failure; distinguish revoked 401 from transport failure. Keep processing leases/ambiguity handling intact. Re-fetch configuration before resume and never revive cancelled jobs.
- [ ] Run existing local-worker, capture, processor, and ownership tests; commit after green.

### Task 4: Tray, singleton, app links, and startup preference
**Files:** Create worker/companion.py, worker/windows_integration.py, tests/test_windows_integration.py; modify worker/requirements.txt and local setup copy.
**Interfaces:** parse_pair_link(value)->str rejects everything except fixed scheme/host/pair path and bounded single code; WindowsIntegration provides single-instance ownership, handoff, protocol registration and per-user startup preference. Tray uses lifecycle from Task 3.
- [ ] Write tests for hostile app links (extra parameters, arbitrary service URLs, fragments, paths, commands, oversized payload), duplicate launches, user-isolated IPC, and startup add/remove preserving unrelated entries.
- [ ] Run focused tests and verify intended failures.
- [ ] Implement a Windows per-user singleton and authenticated/current-user-only IPC for passing a one-time code to the running instance. Never use a shell to dispatch app-link text. Pair through existing service endpoints; clear code from memory after handoff and do not log it.
- [ ] Add tray menu Open ClipBot, Connection status, Start with Windows checkbox, and Quit companion. Open fixed service/setup URLs only. Default launch is windowless and paired launch opens no browser automatically; first run opens setup.
- [ ] Use HKCU protocol/startup registration and precise executable quoting. Startup opt-in is explicit in setup and reversible in tray; application exit releases resources. Test actual duplicate launch, tray appearance, pairing, and quit on Windows.
- [ ] Run full Python checks; commit after green.

### Task 5: Customer installer and isolated build validation
**Files:** Create packaging/companion.spec, packaging/clipbot-companion.iss, packaging/build-companion.ps1, tests/test_companion_package.py; modify .gitignore and LIVE-PIPELINE-TEST.md. Build outputs remain ignored under packaging/dist.
**Interfaces:** Build produces ClipBotCompanionSetup.exe plus manifest containing version, SHA-256, size, unsigned/signed flag, and pinned tool/model provenance. It does not publish externally automatically.
- [ ] Write tests that the build manifest excludes .env, server/data, device.bin, captures/transcripts, test accounts, and developer paths; installer has per-user paths, optional startup consent and uninstall removal for only its own registrations.
- [ ] Run packaging tests and verify failures.
- [ ] Build a windowless PyInstaller directory bundle from an explicit clean dependency list. Include only required model/tool data; use existing verified FFmpeg binaries with provenance/license notices and pinned Whisper model revision. Detect frozen paths so customers need no PATH/Python setup. Include relevant licenses.
- [ ] Compile per-user Inno Setup installer, register the app link, offer startup consent, and provide normal Windows uninstall. Preserve customer media/credentials by default on uninstall; any data-removal option requires explicit customer choice.
- [ ] Validate artifact SHA-256 and contents. Install in an isolated per-user test location, launch without relying on checkout/.venv/PATH, observe no console, tray singleton, and actual model/media-tool readiness. Never claim a clean-machine test from a source-code launch.
- [ ] Public download hosting/signing is a release dependency: supply local tested installer for owner acceptance; only enable public Download after a real binary destination is chosen. Do not publish the private repository or purchase services silently.
- [ ] Run package/local-worker checks; commit after green.

### Task 6: Integration and customer acceptance
**Files:** Modify LIVE-PIPELINE-TEST.md, PRODUCTION-READINESS.md, CONNECTION-READINESS.md; maintain local execution ledger.
- [ ] Run .venv/Scripts/python.exe -m pytest -q, node --test tests/*.test.mjs, git diff --check on the integration tree. Fix failures before integration.
- [ ] Obtain one independent whole-branch review of security, lifecycle, distribution and session boundaries; reproduce and resolve material findings with failing tests.
- [ ] Verify browser controls/status/setup with no companion, installed idle companion, Start acknowledgment, Stop acknowledgment, offline worker, and account switch. Save screenshots; no synthetic live activity.
- [ ] Prepare and push the checked application update under existing authorization. Give exact deployment SHA and tested installer path. Installation/startup consent and public artifact publishing remain explicit user actions where required.
- [ ] Owner installs and pairs through the customer flow; run website Start/Stop with real live scouting and continue collect -> analyze -> render -> queue -> approved publication verification. Report actual receipts and local/server metrics. Do not call the pipeline complete until real acceptance occurs.

## Self-review
Spec sections map to Tasks 1-6. The five review-focus conditions have explicit owning tests. Device acknowledgment never writes browser intent; Start/Stop never bypasses paid analysis/publication safeguards. Installer/local acceptance can proceed while public download hosting remains unavailable, but that dependency must remain visible in both UI and handoff. Native implementation and one final independent review preserve the previously chosen workflow.
