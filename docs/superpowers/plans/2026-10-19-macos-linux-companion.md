# macOS and Linux Companion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox syntax for tracking.

**Goal:** Add secure Apple Silicon, Intel Mac and mainstream desktop Linux companion downloads while preserving the released Windows companion.

**Architecture:** Share the existing worker engine through focused OS adapters. Build native packages independently and select downloads/required versions from an allowlisted platform release catalog. Keep build success and real-device acceptance separate.

**Tech Stack:** Existing Python worker, FastAPI, Vanilla JS, PyInstaller, native Keychain/Secret Service integration, macOS app/DMG and Debian packages.

**Spec:** ../../../MACOS-LINUX-COMPANION-DESIGN.md (approved October 19, 2026).

## Global Constraints

- Repository paths below are relative to launch-release-checkout; execute in a dedicated isolated checkout at implementation time.
- Preserve Windows 0.2.10 artifacts, DPAPI compatibility and existing customer device pairing.
- Support macos-arm64, macos-x86_64 and linux-x86_64; retain windows-x86_64. Initial Linux scope is Ubuntu 24.04/26.04 LTS and Linux Mint 22.x.
- Derive and display minimum macOS versions from actual native dependencies/build artifacts before publication; do not promise every historical macOS release.
- No plaintext secret fallback, secrets in process arguments/logs/artifacts, arbitrary executable PATH fallback in frozen apps, privileged startup service, or customer-plan bypass.
- Keep global Claude stops at $20/day and $400/month; preserve per-user entitlements and worker leases.
- Free build capacity only; verify quota/billing safeguards before dispatch. Do not buy services or make the repository public.
- No production deployment or public Mac/Linux download promotion before native checks and concrete release review. Unsigned Mac distribution requires explicit approval with its actual disclosure.
- Real Mac customer testing is pending; no owner-controlled Mac is available. Report acceptance gaps accurately.

## Review Focus

1. A legacy Windows worker without platform fields must still pair/start; an explicit unknown or contradictory platform must fail (Tasks 1, 4).
2. A locked/missing Linux keyring must show an actionable failure without persisting raw secrets (Task 2).
3. A second application instance or hostile handoff file must not replace a paired account or disclose its token (Tasks 2, 3).
4. A browser with ambiguous Mac architecture must show both downloads rather than silently select an incompatible binary (Task 5).
5. A new Mac version or artifact replaced during transfer must not invalidate Windows compatibility or serve unchecked bytes (Tasks 4, 8).

## Execution and verification conventions

Use the verified project Python environment. Run Python tests with `python -m pytest <paths> -q`; run frontend tests with `node --test <paths>`. First establish these tools exist without installing dependencies. New test modules below are deliberate additions, not existing files. Each task follows failing tests, minimal implementation, passing focused tests and a scoped commit. Never commit generated private files or release binaries as source.

### Task 1: Platform identity and safe adapter boundary

**Files:** Create worker/platforms/__init__.py, worker/platforms/identity.py, worker/platforms/windows.py; modify worker/windows_integration.py, worker/tools.py; add tests/test_platform_identity.py; retain tests/test_windows_integration.py and tests/test_bundled_tools.py.

**Interfaces:** `platform_target(system: str, machine: str) -> str` maps Darwin/arm64 to macos-arm64, Darwin/x86_64 to macos-x86_64, Linux/x86_64 to linux-x86_64 and Windows/AMD64 to windows-x86_64; unknown combinations raise ValueError. `current_target() -> str` reads host identity. Keep existing Windows integration signatures and encrypted-file formats.

- [ ] Add failing test_platform_target_aliases, test_unknown_platform_rejected and test_frozen_tool_native_filename asserting the exact target IDs, unsupported-platform failure, .exe only on Windows, and rejection of missing/symlinked tools.
- [ ] Run those tests and confirm failures are the missing behavior, not environment/import mistakes.
- [ ] Implement identity normalization and the adapter entry point; keep the old Windows module as a compatibility export. Retain existing frozen path containment checks.
- [ ] Run new tests plus existing Windows integration and bundled-tools tests; confirm pass and commit only this task.

### Task 2: Native protected secret storage

**Files:** Create worker/platforms/secrets.py, worker/platforms/macos_secrets.py, worker/platforms/linux_secrets.py; modify worker/credentials.py; add tests/test_platform_credentials.py.

**Interfaces:** `save(path, origin, token)` and `load(path, origin)` retain their current call contract. Native entries are keyed by the absolute private path and origin, so device credentials and temporary handoff codes cannot overwrite one another. Add `delete(path, origin) -> None` for consuming handoffs. Windows delegates to existing DPAPI; Mac uses in-process Security.framework APIs; Linux uses a reviewed, pinned Secret Service binding. Dependency approval/provenance review precedes installation.

- [ ] Add failing tests for origin separation, device/handoff separation, deletion, locked/unavailable storage, token-length limits, and secret-free diagnostics. Assert no token is written to a file or passed to a subprocess on Mac/Linux.
- [ ] Run the new module and verify intended failures.
- [ ] Implement native backends with private metadata paths and no plaintext fallback; retain Windows encrypted file load/save compatibility. Bound reads and normalize friendly errors without including secrets.
- [ ] Run credential tests and existing pairing tests. Native backend tests must run on their actual OS as well as mocked fault tests; record unavailable native runs as pending. Commit source and reviewed dependency changes together.

### Task 3: Desktop lifecycle and URL handoff

**Files:** Create worker/platforms/posix_integration.py, worker/platforms/macos.py, worker/platforms/linux.py; modify worker/companion.py and worker/local_app.py; add tests/test_posix_integration.py and tests/test_platform_lifecycle.py.

**Interfaces:** Each platform provides `user_directory() -> Path`, `SingleInstance` with `.primary` and `.close()`, `startup_enabled() -> bool`, and `set_startup(enabled: bool) -> None`. Shared `parse_pair_link(value)` retains existing strict parser behavior. Add `deliver_pair_link(value: str) -> None` to validate and submit application URL events through the same protected one-time handoff path.

- [ ] Add failing tests for user-private directories, lock contention/release, malformed and duplicate URL parameters, symlink/other-user handoff rejection, stale handoff consumption and graceful shutdown.
- [ ] Run new tests and confirm expected failures.
- [ ] Implement POSIX advisory locking, private paths, protected handoff deletion using Task 2, Mac application URL events and per-user login startup, Linux desktop URL registration/autostart. Use fixed executable paths and structured quoting; no shell interpretation of links.
- [ ] Run lifecycle and existing companion tests. Check launch/quit and tray behavior on native desktops separately; do not equate headless tests to desktop acceptance. Commit the task.

### Task 4: Platform-aware release catalog and worker compatibility

**Files:** Create server/companion_releases.py; modify server/companion_download.py, server/companion.py, server/companion_api.py and worker/runtime.py; add tests/test_companion_release_catalog.py and tests/test_companion_platform_api.py.

**Interfaces:** `ReleaseCatalog(root: Path)` exposes `installer(target: str) -> OwnerInstaller | None` and `required_version(target: str) -> str | None`. Reuse verified installer hashing/stream identity protections. Extend reports with `platformTarget`; absence means legacy Windows only. Extend status/download/beta-accept requests with optional `target`, validated against the same four target IDs. Existing no-target Windows calls remain compatible. Device reports select compatibility only, never entitlements.

- [ ] Add failing tests for four-target selection, legacy Windows reports, unknown target and path traversal rejection, mismatched acknowledgement hashes, no cross-target version gate, unpublished/missing target failure, and changed-on-disk artifacts refusing transfer.
- [ ] Run new tests and confirm intended failures.
- [ ] Implement the allowlisted catalog with target-local manifests, explicit content-disposition filenames and independent promotion metadata. Retain the legacy Windows directory mapping. Preserve ownership, email/policy/plan/lease and beta acknowledgement checks on every path.
- [ ] Run new tests and all existing companion download/public-release/unsigned-beta/paid-worker suites; commit after passing.

### Task 5: Website platform selection and patch notes

**Files:** Modify frontend/js/controllers/companion-controller.js, frontend/js/views/companion.js and frontend/js/release-notes.js; create frontend/js/companion-platform.js; add tests/companion-platform.test.mjs; extend tests/companion-download-actions.test.mjs and tests/companion-update-notice.test.mjs.

**Interfaces:** `recommendPlatform({platform,userAgent}) -> {os: string|null, targets: string[]}` recommends an OS only; Mac returns both architecture choices when uncertain. Carry the selected allowlisted target through status, acknowledgement and download URLs. Keep update checks tied to the paired worker target, independent of a manual download selector.

- [ ] Add failing tests for ambiguous Mac detection, manual overrides, unsupported targets, escaped metadata, unavailable-package messaging and Mac release changes leaving a Windows update prompt unchanged.
- [ ] Run new and existing companion frontend tests and verify intended failures.
- [ ] Implement clear Windows/Mac Apple Silicon/Mac Intel/Linux labels, minimum-OS text from verified release metadata, copy-code fallback and target-specific release notes. Do not expose a download link for an unavailable package.
- [ ] Run companion frontend tests; inspect actual modal layout at narrow/wide widths and keyboard navigation. Commit after passing.

### Task 6: Native dependency verification and build recipes

**Files:** Create packaging/native-companion.spec, packaging/build-native.py, packaging/platforms/macos.json, packaging/platforms/linux.json, tools/verify_native_release_inputs.py and tests/test_native_release_inputs.py; update packaging_audit.py only where native-package structure needs recognition.

**Interfaces:** `python tools/verify_native_release_inputs.py --target TARGET --inputs PATH` fails nonzero on unreviewed/mismatched inputs. `python packaging/build-native.py --target TARGET --output PATH` requires clean committed source, a matching native host, verified pinned inputs and builds app/DMG on Mac or .deb on Linux. Emit target, architecture, minimumOS, version, sourceCommit, sha256, sizeBytes, signed, provenanceVerified and acceptance status. Never infer signed/notarized/accepted from build success.

- [ ] Add failing tests for wrong host/architecture, altered wheels/tools/models, missing corresponding sources/licenses, dirty source, secrets/customer files in bundles and mismatched minimum-OS/library metadata.
- [ ] Run verifier tests and confirm intended failures.
- [ ] Build a reviewed platform-specific dependency inventory, including native video/transcription libraries and corresponding source obligations. Implement native PyInstaller recipes, app identifiers/URL registration and Debian desktop/dependency metadata. Preserve Windows verifier restrictions.
- [ ] Run verifier and package-audit tests; commit source recipes and approved pinned inventories. A missing reconstructable dependency is a release blocker, not a reason to skip provenance checks.

### Task 7: Free native build execution

**Files:** Create .github/workflows/companion-native.yml and tests/test_native_build_workflow.py only after checking hosting/quota constraints; add docs/releases/native-build-instructions.md.

**Interfaces:** Manual dispatch accepts target plus an existing reviewed commit. Use fixed native runner labels verified against current official runner documentation, read-only repository permissions, immutable action revisions, 45-minute job timeout and 7-day artifact retention. No production credentials, untrusted PR release execution or automatic builds on ordinary pushes.

- [ ] Read repository visibility, Actions availability, remaining included capacity and billing controls without printing credentials. Establish a free execution path before dispatch; otherwise record the exact capacity blocker and continue unaffected work.
- [ ] Add failing workflow-policy tests asserting the restrictions above; implement the workflow and rerun to pass.
- [ ] Commit reviewed workflow, dispatch only within verified free capacity, and obtain independently hashed native artifacts and verification reports. Do not claim Mac/Linux packages exist until the jobs actually succeed.

### Task 8: Packaged runtime and full security/regression acceptance

**Files:** Create tools/accept_native_companion.py, tests/test_native_acceptance.py and docs/releases/native-companion-acceptance.md; extend existing packaged diagnostic entry points in worker/companion.py as necessary without starting scouting or making AI calls.

**Interfaces:** `python tools/accept_native_companion.py --target TARGET --artifact PATH --report PATH` emits checks with passed/failed/not-exercised status; overall passing build diagnostics do not mark real-desktop acceptance complete.

- [ ] Add failing acceptance tests ensuring missing/wrong-architecture artifacts, failed diagnostics, changed hashes and unexercised desktop checks cannot become accepted release evidence.
- [ ] Implement and run native packaged diagnosis, model loading, synthetic-media capture/render/transcription and artifact audit. Check no production credentials or customer media enter reports/packages.
- [ ] Run all Python tests and `node --test tests/*.test.mjs`, plus Windows packaged smoke checks. Exercise protected download errors, platform independence, security-header/origin handling, user isolation and unchanged budget gates.
- [ ] Obtain independent whole-branch code/security review; fix findings and rerun affected tests. Commit reviewed fixes and acceptance evidence without secrets.

### Task 9: Controlled beta downloads and customer verification

**Files:** Create docs/releases/native-companion-beta-checklist.md and extend the patch tracker; prepare release manifests and per-target promotion tooling without modifying released Windows bytes.

**Interfaces:** Release evidence identifies exact source/artifact hashes, OS/architecture, minimum OS, signature state, native build checks and real-device acceptance. Keep owner-only candidate access distinct from public customer release. Existing public beta rules requiring clean-install/pairing acceptance remain enforced; do not relax them silently to deliver an unaccepted build.

- [ ] Verify a free artifact delivery location has sufficient space and supports the existing protected-download contract; retain rollback artifacts without exhausting Render disk.
- [ ] Prepare the exact Mac signing/notarization or unsigned-beta disclosure and seek approval for the concrete release choice before distribution. No purchase is implied.
- [ ] Arrange a narrowly scoped candidate path for the designated beta tester, retaining account/policy/artifact acknowledgement protection and explicitly recording incomplete clean-machine acceptance. Review and approve that concrete access change before enabling it; never open all customer downloads as a workaround.
- [ ] Have the Mac tester report processor/OS and exercise install, pairing, Start/Stop, clip processing, restart and upgrade; collect sanitized evidence. Obtain Linux desktop acceptance for each claimed distribution or label it unverified rather than supported.
- [ ] Promote only targets with their required checks satisfied after release review. Verify live download hash, correct target selection, Windows continuity and rollback readiness; update patch notes/tracker with actual outcomes.

## Completion reporting

Report separately: implemented source; native builds available; automated/security checks passed; real-device checks passed; approved and published targets; remaining blockers. No package availability, signature, licensing/provenance, native compatibility or production readiness claim without recorded evidence.
