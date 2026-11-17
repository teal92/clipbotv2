# Live scout-to-publish implementation plan

> For agentic workers: use superpowers:executing-plans to implement this plan task by task. Native execution in the existing project; focused independent review before integration.

**Goal:** From the customer website, run concurrent Twitch/Kick scouts, ingest a genuinely discovered live moment, analyze, render, queue and publish it using the owner's connected test accounts.

**Architecture:** Extend the v2 paired worker and encrypted account OAuth. Server owns configuration, metadata, authenticated orchestration, budgeted Claude requests and publication reconciliation. Local worker owns capture, transcription, rendering, preview and direct provider media transfer. Existing v1 code is read-only reference and is reused only as isolated reviewed routines.

**Tech stack:** Existing FastAPI/SQLite prelaunch service, official Anthropic SDK, httpx, vanilla JS; worker-only yt-dlp, local Whisper and FFmpeg integrations. Exact new dependency versions are selected from official current releases during prerequisite verification and documented before installation; never added to Render merely for local processing.

**Spec:** ../specs/2026-10-11-one-clip-pipeline-design.md (live revision approved by owner).

## Global constraints
- No raw media on Render. No developer secrets, Claude key or encryption key on the worker or in browser storage.
- Worker authorization always resolves account from the paired device; browser writes retain session, CSRF and exact-Origin protection.
- Favorites/forced/category selection respects existing paid scout and preference coverage; force never bypasses limits or means publish.
- Two then four simultaneous real live sources, then account limit only if measured load is healthy; five-minute observations per step.
- Clip length 15–60 seconds, score threshold 75, center-crop preview explicitly labeled until smart layout exists.
- Haiku 5.5, default-off dispatch, initial test ceiling $0.05 subordinate to existing global/account/daily safeguards; no automatic retries.
- Starter/Creator: 20 distinct successful clips per UTC day; Pro/Custom have no ClipBot posting cap. Cross-post once per clip; unknown outcomes reconciled before retries.
- Preview, caption and destination approval before the first post. Facebook first, Instagram and TikTok individually afterward.
- Keep all five tested OAuth integrations intact; connected is distinct from publishing verified.

## Review focus
- Account switch or worker revocation during a leased job must not reveal another user's state or credentials (tasks 1/4).
- Offline favorites, overlapping forced/category matches and plan changes must not waste slots or exceed coverage (task 1).
- Source disappearance, disk exhaustion and processing backlog must pause or cancel captures cleanly (task 2).
- Invalid model output, billed errors and timeouts must settle or retain conservative reservations without duplicate paid calls (task 3).
- Upload timeout/restart, malicious provider upload URL and repeated Publish clicks must not leak tokens or duplicate a post (task 4).

### Task 1: Account-owned scout control and worker job boundary
**Files:** create server/scouts.py, server/worker_jobs.py, server/worker_api.py, worker/scout_scheduler.py; modify server/store.py, server/app.py, worker/client.py; tests/test_scouts.py and tests/test_worker_jobs.py.
**Interfaces:** ScoutStore(store).save(uid, selection) -> configuration; snapshot(uid) -> configuration/status. select_sources(config, live_sources, scout_limit) -> ordered unique source list. WorkerJobs.claim(device_token) -> bounded leased job or None; report(device_token, job_id, lease_id, event) -> state. Device auth resolves uid internally; never accepts caller uid.
- [ ] Write tests: wrong account cannot read/write selections or report jobs; token revoke rejects claims/events; simultaneous leases have one owner; offline pinned source consumes no capture slot; forced precedes favorite precedes category; overlap yields one source; favorites/categories/pins exceeding current coverage are rejected.
- [ ] Run new tests and verify expected failures before implementation.
- [ ] Implement tables/indexes, device-auth helper, validated scout configuration, ordered selection and lease/CAS state transitions. Use server-owned opaque IDs and bounded payloads.
- [ ] Run pytest tests/test_scouts.py tests/test_worker_jobs.py tests/test_worker.py tests/test_oauth.py -q; all pass, including existing pairing/OAuth contracts.
- [ ] Review and commit this independently testable control boundary.

### Task 2: Real provider discovery and bounded local capture
**Files:** create worker/discovery.py, worker/capture.py, worker/runtime.py, worker/prerequisites.py, worker/requirements.txt; modify worker/client.py; create tests/test_capture.py and tests/test_discovery.py.
**Interfaces:** discover(config, platform_access) -> validated LiveSource records with provider ID/category/live state; capture(source, job_directory, stop_event) -> bounded local media window; prerequisites() -> structured tool/model readiness. Runtime consumes Task 1 selections and reports measured stage events through WorkerJobs.
- [ ] Write tests: offline/unavailable source produces no fake media; private/unsupported source fails visibly; allowed provider URLs only; duplicate processes suppressed; capture stopped on cancellation, low disk or bounded queue saturation; unsafe shell input cannot become executable text.
- [ ] Verify expected failures, then document official provider capabilities and package/model downloads. Announce downloads before installation. Inspect v1 scouts for reusable algorithms, not shared credentials/database.
- [ ] Implement official source discovery where available and worker-side capture using argument arrays/timeouts. Unsupported Kick category capability stays explicitly unavailable pending a supported route. Bound queued windows to two and one transcription/render job initially; capture window max five minutes, disk headroom minimum 2 GiB. Report pause reasons and actual metrics.
- [ ] Run pytest tests/test_capture.py tests/test_discovery.py tests/test_scouts.py tests/test_worker_jobs.py -q. Use a tiny local generated fixture only for encoding unit tests; it cannot satisfy live acceptance.
- [ ] Review and commit. No live capture until account/source configuration and prerequisites are ready.

### Task 3: Local transcription and budgeted Davey analysis
**Files:** create worker/transcribe.py, server/analysis.py, server/analysis_api.py; modify server/app.py and server/budgets.py only for required settlement interfaces; create tests/test_analysis.py and tests/test_transcribe.py.
**Interfaces:** transcribe(media_path) -> timestamped transcript segments. AnalysisService.analyze(uid, job_id, transcript, context) -> validated Candidate or failure/pending outcome. Use BudgetLedger.reserve and settle; request identity is durable and idempotent. Candidate includes source/job IDs, start/end, score, rationale and platform drafts.
- [ ] Write tests: dispatch disabled or no eligible allowance never calls provider; concurrent/replayed request does not dispatch twice; malformed timestamps, source-window escapes and below-threshold results cannot auto-advance; injected transcript instructions cannot create tools/commands; billed invalid output settles costs; unknown provider outcome retains reservation and suppresses retry.
- [ ] Verify expected failures. Verify current official Haiku pricing and SDK usage fields; enforce counted input <=8,000 tokens and output <=1,000 tokens. Reserve worst-case conservative cost before calling; no tools, caching, thinking or automatic retries for this first adapter.
- [ ] Implement local Whisper and official pinned-endpoint Anthropic adapter, strict candidate validation, usage accounting and fail-closed reservation lifecycle. Do not persist raw transcripts to shared evidence or logs. Retain beta acknowledgment requirements.
- [ ] Run pytest tests/test_analysis.py tests/test_transcribe.py tests/test_backend.py -q plus existing budget tests. All pass before enabling a single bounded live call.
- [ ] Review and commit. Owner test dispatch activation remains separate from public automatic dispatch.

### Task 4: Render, publication broker and durable delivery
**Files:** create worker/render.py, worker/upload.py, server/publication.py, server/publication_api.py; modify server/app.py and OAuth helpers only for selected-destination access; create tests/test_render.py and tests/test_publication.py.
**Interfaces:** render(candidate, media_path, transcript, output_directory) -> validated MP4 artifact/hash. PublicationService.prepare(uid, clip_id, destination, reviewed_options) -> job-scoped direct upload instructions; reconcile(uid, attempt_id) -> confirmed/pending/failed receipt. Worker uploads directly and reports bytes/completion, never claims success solely from HTTP upload acceptance.
- [ ] Write tests: render range and paths cannot escape job root; output is 1080x1920 H.264/AAC with expected duration/subtitles; cross-account artifact/destination denied; expired or revoked OAuth blocks preparation; upload URL host/path/redirect attack rejected; token never reaches browser JSON/logs; duplicate clicks/crashes/timeouts cannot repeat unknown publication.
- [ ] Add atomic concurrent cap tests: at 19 Starter/Creator clips only one new distinct clip can reserve final slot; cross-post/retry does not count twice; confirmed failure releases reservation; pending receipt blocks duplicate retry; Pro/Custom posting is not capped but all other safeguards apply.
- [ ] Verify expected failures, then implement official Facebook/Instagram resumable and TikTok FILE_UPLOAD flows. Query TikTok creator-info and require supported privacy/settings/express consent. Reuse selected v1 render algorithms only after validation; do not reuse global token store or environment fallback.
- [ ] Run pytest tests/test_render.py tests/test_publication.py tests/test_oauth.py -q and verify no credential strings in captured browser responses or logs.
- [ ] Review and commit. publishingReady reflects actual capability and authorization, not presence of a saved account.

### Task 5: Website controls, local launcher and real stage displays
**Files:** modify frontend/js/views/streamers.js, frontend/js/views/clips.js, frontend/js/views/processing.js, frontend/js/views/publishing.js, frontend/js/views/connections.js, frontend/js/service-state.js, frontend/js/app.js; add frontend/js/controllers/scouts-controller.js and pipeline-controller.js; add worker/local_app.py and start-worker.ps1; create tests/scouts.test.mjs, tests/pipeline.test.mjs and tests/test_local_worker.py.
**Interfaces:** website consumes scout configuration and job/receipt snapshots; approval writes identify owned durable clip IDs. Loopback worker serves only approved job previews using short-lived per-artifact capability URLs, accepts exact trusted website Origin where required and never exposes arbitrary files; generated local setup secret protects pairing/file operations. Remote HTTPS page preview capability is validated in supported browsers; if blocked, open protected local preview tab with clear return-to-ClipBot approval step.
- [ ] Write tests: malicious source/caption escaped; refresh/route change restores actual jobs; offline state never claims monitoring; favorite/pin/category changes persist within limits; publication consent/destination required; local file traversal, foreign Origin and missing secret denied; stop/revoke UI acts on correct account.
- [ ] Verify expected failures. Implement pairing launcher without keys/passwords, truthful prerequisites, source search/favorites/pins/categories and start/stop controls. Keep all connections in Connect Accounts. Add bounded event/status refresh and actual queue/preview/publish states; no seeded clips/counters.
- [ ] Run node --test tests/*.test.mjs and full pytest -q. Inspect real desktop/mobile UI and browser-to-local preview behavior; screenshot proof for changed flows.
- [ ] Review and commit. Document exact owner deployment/start steps and rollback.

### Task 6: Live acceptance and measured scaling
**Files:** create LIVE-PIPELINE-TEST.md; update CONNECTION-READINESS.md and PRODUCTION-READINESS.md current-status sections without erasing historical increments.
**Consumes:** Tasks 1–5, owner-connected accounts, compatible local prerequisites and authorized live sources. **Produces:** measured results with real clip/job/receipt references; no keys, raw token data or fictitious scores.
- [ ] Deploy verified commit; pair local worker through the site; confirm account coverage and beta acknowledgment. Announce any dependency/model download and bounded paid analysis activation.
- [ ] Configure live sources through ClipBot. Observe two sources for five minutes, then four if plan/hardware permits. Check forced, favorite, category and offline-source behavior and no duplicate monitors. If categories or suitable live content are unavailable, report that exact blocker without substituting pre-made media.
- [ ] Carry a naturally captured candidate through transcription, bounded real analysis, rendering and queue. Reject/approve through website; verify budgets, preview and source attribution. Publish one approved clip to Facebook and reconcile its provider receipt.
- [ ] Test Instagram and TikTok individually from reviewed queued content with required settings. Record each platform result separately, including restrictions. Verify retries, stop/restart, device revocation and actual metrics.
- [ ] Record local CPU/RAM/disk/network/backlog and server latency/failure/memory/queue measurements; run deterministic two-account isolation/concurrency checks. Do not interpret one owner test as public capacity proof.
- [ ] Run final full suites after any correction; independent final review; push and report completed stages and remaining platform/load limitations honestly.

## Review gate and execution
Design approved. This plan is ready for owner review as required by writing-plans before implementation. Recommended execution is native in this chat, using the existing project and one focused independent review per completed interface increment. No new scout, dependency download, paid analysis or publication has started during planning.
