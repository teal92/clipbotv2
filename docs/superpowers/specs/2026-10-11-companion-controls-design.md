# Website Start/Stop and background companion design

## User request and success criteria
The customer uses ClipBot through the website. Add green Start ClipBot and red Stop ClipBot buttons in the header before the existing worker status and Account button. First Start explains that local processing needs a one-time companion installation. The companion stays in the Windows system tray, starts at sign-in when the customer agrees during setup, and receives Start/Stop commands from the website. Customers do not execute scripts or commands.

Windows is the initial target, matching the owner's test machine. Mac/Linux support must not be advertised as available. Existing connected platform accounts, plan coverage, review/publishing consent, and budget stops remain in force.

## Status contract
Use actual authenticated companion heartbeat and reported processing state rather than browser-tab presence.
- Offline: no healthy paired companion heartbeat; Start opens the setup/reconnect prompt.
- Ready: paired companion is connected and idle; Start can request monitoring.
- Starting: website requested monitoring, awaiting companion acknowledgment.
- Running: companion acknowledged monitoring and its heartbeat is fresh. Show actual active scout count separately; offline sources need not mean the companion stopped.
- Stopping: Stop requested, awaiting capture cancellation acknowledgment.
- Paused/Needs attention: companion reports a budget, coverage, beta acknowledgment, local tool, authorization, or network problem. Explain the next action.
Never label a requested run as Running before acknowledgment. Stop is always available for an outstanding requested run, even if its worker went offline.

## First Start and setup
The modal says: 'ClipBot uses a small companion on this computer to monitor streams and process videos locally. It runs in the system tray while you control ClipBot here. Your computer must stay on.' Offer Download for Windows, Connect installed companion, and Cancel.
Provide a real downloadable installation artifact, version/checksum, and clear startup/permission information. Do not link to a missing installer or expose the private source repository. Until a public download destination is available, a local installer can be used for owner testing but the public download button must explain unavailability rather than claim setup is ready.
The installer includes the runtime, necessary local media tools and pinned model, or explicitly performs bounded prerequisite downloads from official sources with progress. No Python/pip/terminal setup for customers. It contains no platform secrets, account tokens, server environment files, or user media. Install per Windows user without requiring administrator privileges where possible. Ask during setup whether to start at Windows sign-in. Provide normal uninstall/startup removal.
A first-run welcome page guides account pairing. Prefer a website-generated one-time pairing handoff to the installed companion through a registered app link with explicit user action. Pairing codes are short-lived/single-use and are not logged. If the browser declines the app link, provide a clear manual code fallback; do not require social credentials or API keys.

## Normal operation
A paired companion launches hidden into the tray and polls the account's existing authenticated configuration. The tray menu offers Open ClipBot, Connection status, Start with Windows preference, and Quit companion. It does not open a terminal. A singleton guard prevents duplicate workers; launching it again opens the existing setup/status page.
Website Start preserves forced/favorite/category preferences, validates allowance and worker readiness, and starts monitoring via a protected account-owned request. If no slots were chosen, choose a safe default of at most two within plan/local capacity and show the selection. Stop cancels current scouting promptly but keeps the companion alive and account pairing intact. Previously completed review/ready clips remain available. Any active upload is reconciled and never automatically repeated; Stop does not pretend it can undo a provider-accepted publication.
Closing the browser does not stop a requested run. Closing/quitting the companion stops local processing and eventually reports Offline. Revoked account/device access halts captures/processing and invalidates previews. An inactive subscription or spending stop cannot be bypassed by Start.

## Security and efficiency
Keep existing exact Origin/CSRF checks and tenant isolation for service control. Extend heartbeat with tightly validated readiness/run acknowledgment and bounded metrics, never secrets or raw model transcripts. A browser cannot directly control another user's worker. Loopback endpoints remain exact-host/exact-origin protected; no permissive CORS or web-accessible process execution. App-link parsing accepts only a fixed pairing operation and bounded code, never shell commands or arbitrary URLs/paths. Windows DPAPI protects saved pairing. Startup changes are explicit and reversible.
Retain local media capture/render/upload, default two captures and bounded queues, existing budget reservations and no automatic paid retries. The tray is idle when stopped. Add connection retry/backoff for temporary outages without marking healthy state or reviving cancelled work.

## Implementation boundaries
Frontend: header controls/status, first-use modal, install/pair guidance, account-generation-safe polling, and clear error states.
Service: account-owned Start/Stop endpoint preserving scout selection, readiness/acknowledgment heartbeat state, and safe download metadata.
Companion: shared lifecycle controller, tray entry point, singleton/app-link handoff, explicit startup preference, health/run acknowledgment, and customer installer/build recipe. Development .cmd launchers are no longer the customer setup path.
Distribution: choose a public binary-only download destination before enabling the public Download button. Do not silently publish the existing private repository. Code signing availability determines whether a Windows publisher warning must be disclosed; never describe an unsigned beta installer as signed or verified by Windows.

## Validation and acceptance
Write failing tests for: header start/stop state; uninstalled/offline setup modal; tenant/CSRF denial; Start preserving preferences and honoring plan caps; Stop/offline behavior; stale/acknowledged heartbeats; session switches; singleton; hostile app-link inputs; revocation; startup install/uninstall; and cancellation during processing.
Run full backend/frontend checks and desktop/responsive browser verification. Build/install on the owner's Windows machine, verify no terminal window, tray presence, automatic startup configuration, pairing through the customer flow, and website Start/Stop acknowledgment. Then continue the real live scout pipeline test. A development launcher or mocked capture is not acceptance evidence.

## Open release dependency
Public installer hosting and signing credentials are not currently configured. Build and validate the installer locally first; publish only the binary artifact through an explicitly chosen public destination. No extra paid service purchase is assumed.
