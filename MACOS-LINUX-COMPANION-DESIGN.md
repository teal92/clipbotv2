# ClipBot macOS and Linux companion design

Date: October 19, 2026
Status: Written design for user review; implementation has not started.

## Outcome and scope

Customers use the existing ClipBot website, subscription and pairing flow with a native companion for their computer. Support both Apple Silicon and Intel Macs, rather than building only for the first waiting customer. Support mainstream desktop Linux initially: Ubuntu 24.04/26.04 LTS and Linux Mint 22.x on x86-64. Do not claim support for every historical macOS release, Linux distribution, or processor.

Build and security checks precede customer distribution. The waiting customer will be the first real Mac beta tester; no owner-controlled Mac is available. Clearly identify that distinction in release acceptance records. Minimum macOS versions must be derived from the native dependencies and built artifacts and shown beside downloads before publication; do not advertise an unverified minimum version.

The working Windows 0.2.10 release, installed pairing, customer plans and global Claude spending stops remain unchanged by this port. Missing-title model handling is a separate pending improvement.

## Approach

Recommended: retain one companion engine with small OS-specific adapters and native builds for each target. This shares capture, analysis, processing and API behavior while isolating credential storage, startup, tray integration and packaging.

Alternatives considered: maintaining separate companion implementations would duplicate security fixes; replacing the companion with remote processing would change operating costs and the product architecture. Neither is needed for this request.

## Packages and customer experience

- Windows x86-64 keeps its existing installer and release track.
- macOS Apple Silicon and Intel receive separate native application packages. The download page names both processor types clearly and explains how to identify them.
- Linux x86-64 receives a Debian package for the supported Ubuntu/Mint desktop families. Publish required desktop/keyring dependencies and the tested distribution list.
- Recommend the detected OS but always expose a manual platform choice. Browser detection is a convenience, never authorization, and must not silently guess a Mac's processor.
- Preserve the existing one-time pairing and installed-companion launch flow, using native application URL registration. Provide the existing copy-code fallback when browser handoff fails.
- Show a clear error for unavailable secure credential storage, unsupported architecture, missing desktop integration, or incompatible versions. Never silently store pairing credentials in plaintext.
- Patch notes and update prompts describe the customer's own platform release. Never replace a released artifact under its old version/hash.

## OS integration

Introduce a focused platform interface for application data paths, single-instance protection, secure credentials, optional login startup, application URL handoff and bundled-tool paths.

Keep Windows DPAPI protection. Store Mac credentials through native Keychain APIs without passing secrets on command lines. Use the desktop Secret Service on Linux and fail closed if it is unavailable or locked. Resolve any additional library through the dependency review and pinning process before installation.

Use native per-user file locations and permissions. Single-instance coordination and URL handoff must reject other-user interference, malformed requests and replayed/expired pairing codes. Preserve loopback-only serving, browser-origin protections and ownership checks.

Use per-user login startup where supported; do not install privileged background services. Document platform-specific startup limitations. Quitting must stop work and free device/process locks cleanly.

Frozen apps execute only their verified bundled tools using native filenames. Preserve symlink/path-escape protections; do not substitute arbitrary executables from PATH.

## Server and release compatibility

Replace the single-installer assumption with an explicit release catalog keyed by supported OS and architecture. Paths come only from server-owned configuration and an allowlist, never from arbitrary download query text.

Each release records platform, architecture, version, minimum OS, hash, size, source commit, signing/provenance status and acceptance results. Downloads retain account authorization, current-policy acceptance and artifact-specific beta acknowledgement.

Worker reports include platform and architecture for compatibility selection. These fields grant no access or entitlements. Legacy Windows reports continue working under an explicit legacy-Windows rule. Unknown or contradictory targets fail clearly rather than receiving the wrong installer.

Select minimum supported versions independently for each target. Publishing a new Mac build must not require Windows users to install it. Rollback and promotion are platform-specific. Do not put additional large artifacts on the nearly full production disk without first validating capacity and a free hosting/delivery path.

## Native builds, dependencies and cost

Build macOS artifacts on macOS and Linux artifacts on Linux. Do not rename or reuse Windows binaries. Create platform-specific pinned dependency inputs and native-library provenance records while retaining the current Windows verification rules.

Verify video capture/rendering tools, transcription model files, PyAV/FFmpeg native dependencies, source/license obligations and executable architectures on each target. A passing Python unit suite alone is not acceptance of a packaged native app.

Use only free build capacity. Before dispatching hosted builds, verify repository visibility, included quota and billing safeguards. Do not make the repository public or purchase runner time, certificates, Apple memberships or other services. If free native build capacity cannot be established, complete unaffected source work and report the concrete build blocker.

Use narrowly scoped workflow permissions, pinned build actions and dependencies, bounded job duration and limited artifact retention. Keep production credentials out of packaging jobs and artifacts. Do not run privileged release jobs from untrusted pull requests.

Existing unsigned-Windows beta approval is not represented as Apple signing or notarization. Do not publish a Mac package with misleading publisher/verification claims. Any unsigned Mac beta must disclose its status before download, must not instruct customers to disable security software, and needs explicit approval of that concrete distribution choice before publication.

## Security and regression answers

1. Secure approach: retain all server-side access, leases, quotas and token validation; add native protected credential storage, audited dependencies and verified per-target artifacts. Validate with adversarial tests before making a security completion claim.
2. Efficient approach: share the existing engine and introduce narrow OS adapters; produce independent native packages without duplicating the application.
3. Possible regressions: Windows pairing/startup, update prompts, wrong-architecture downloads, tray behavior, localhost browser restrictions, model/native-library loading, installer upgrades, credential migration and production disk capacity.
4. Required tests: the matrix below plus the existing Windows backend/frontend/security regression suites. Do not call the port ready from source inspection alone.

## Acceptance matrix

- Unit/security: secure storage round-trip and failure handling; private file permissions; single-instance contention; malformed URL/query rejection; expired/replayed pairing; no secrets in logs, process arguments or artifacts; bundled-tool path attacks.
- API: authorized downloads per target, unknown target rejection, ownership/policy enforcement, per-artifact acknowledgement, legacy Windows compatibility, independent required versions and rollback.
- Native packaging: correct architecture and library loading; packaged diagnosis; model load; captured-media processing and vertical rendering; dependency/source inventory; secret scanning; artifact hash/size checks.
- Desktop behavior: fresh install, launch, pairing, tray/menu behavior, browser handoff, Start/Stop, optional login startup, restart, update and uninstall on each claimed target. Linux headless CI does not prove desktop tray/keyring behavior.
- Customer isolation: subscription gates, worker leases, review limits and the unchanged $20/day and $400/month global stops still apply.
- Website: platform selector, clear processor labels, protected downloads, copy-code fallback, platform-specific update/patch notes and useful unsupported-platform errors; Safari, Firefox and Chrome coverage where available.
- Real Mac beta: ask the tester to confirm Mac processor/OS when testing, install, pair, start/stop, process a clip, restart and update. Record what was actually exercised. Missing hardware or desktop evidence remains visible as an acceptance gap.

## Delivery sequence

After written-design review and the required implementation-plan review: establish OS adapters and regression tests; add platform-aware release selection; implement and verify the Apple Silicon and Intel builds; produce Ubuntu/Mint packages; run package/security checks; prepare clearly labeled beta downloads; obtain real-device acceptance and promote each verified target independently.

Never label an unbuilt or untested package ready. Report source completion, successful native builds and real-device acceptance separately.
