# Davey phase progression implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans inline, task by task, with one fresh whole-branch review at the end. Steps use checkbox syntax for tracking.

**Goal:** Make personal adaptation and measured phases real, then provide explicit customer-controlled autonomous posting with server-enforced eligibility.

**Architecture:** Keep the base Haiku model, customer-local memory/render/upload and existing durable publication broker. Add server-owned consent, policy revisions, prediction/evaluation metadata and phase decisions; export only consented bounded reason counts. Reuse existing lease, budget, paid-access and publication guards. No live release switch is enabled by implementation.

**Tech stack:** Existing Python/FastAPI/SQLite/Anthropic SDK and vanilla JavaScript; no new dependencies.

**Spec:** ../../DAVEY-PHASE-DESIGN-2026-10-15.md

## Global constraints

- Base model remains the existing pin; no fine-tuning or customer API keys.
- Global Claude limits remain $400/month and $20/day; existing plan limits remain enforced.
- Notes and feedback files stay local. Optional reason summaries contain at most 200 confirmed decisions and listed labels/counts only.
- Phase 3 requires 100 manual decisions; phase 4 requires >=25 new validation decisions, >=90% agreement, >=20 predicted approvals and >=95% approval precision with no unresolved incident.
- Automatic decisions never increase human decision or validation counts.
- Final phase unlocks off-by-default controls; customer explicitly opts in and selects supported destinations/sources/caps.
- TikTok remains user-confirmed. Automatic Instagram/Facebook require real platform acceptance before the independent CLIPBOT_AUTONOMY_ENABLED switch can be turned on.
- No paid AI calls, real posts, email sends, public signup or production billing activation in automated tests.

## Review focus

- Consent or Stop changes between provider preparation, upload grant and final publishing must prevent new automatic dispatch.
- Edited/repeated/automatic feedback must not inflate held-out qualification.
- Context/model changes invalidate stale validation without invalidating every routine new feedback record.
- Legacy cached analysis lacking automation safety metadata remains manually reviewable and cannot become an automatic post.
- Account/device/destination swaps must never transfer memory, eligibility or publication permission.

## Task 1: Unify current customer worker authorization (audit fix)

Files: server/worker_api.py, worker/runtime.py, tests/test_customer_analysis_release.py.
Interfaces: existing customer_enabled(store,uid); produce authenticated customerAnalysisEnabled config flag distinct from betaAccepted.
- [x] Reproduce eligible customer receiving analysisEnabled=false; preserve negative switch/mode/email/policy tests.
- [x] Reuse customer_enabled and leave real betaAccepted unchanged.
- [x] Reproduce runtime beta gate still blocking the production path; use customerAnalysisEnabled only to distinguish existing production authorization from legacy owner-test acknowledgment.
- [x] Verify actual fake-task allocation and heartbeat errors; no captures/model calls.
- [ ] Commit audit fix and evidence.

## Task 2: Durable phase and consent authority

Create server/davey.py and tests/test_davey_progression.py. Modify server/app.py and server/store.py.
Interfaces: DaveyStore(store).settings(uid), status(uid), save(uid,values), prediction(uid,job,candidate,context_key), evaluate(db,uid,candidate_id,decision), context_key(uid).
Data: account-owned settings/revision, immutable pre-review predictions and one latest human evaluation per candidate. Store only hashes and bounded policy/decision metadata, not transcripts/notes/summaries. Phase calculations use current model/policy/selection context and distinct actual human reviews.
- [ ] Write red tests for exact boundaries (0/1/99/100, 24/25 validation, 22/25 vs 23/25 agreement, 19/20 precision), account isolation, duplicate/edit resistance, missing prediction, automatic exclusion, model/preference revision reset and opt-in rejection before qualification.
- [ ] Implement strict settings (personalContext false, shadowEnabled false, automatic false, platforms [], dailyPostLimit 3, minScore 90, sources [], rightsAccepted false); platform allowlist Instagram/Facebook; source identity allowlist; max 100 daily automatic clips further limited by the paid plan.
- [ ] Reject unknown fields, booleans as integers, unqualified shadow/auto changes and forged state. Only server computes phase. Save explicit consent/revocation revisions.
- [ ] Add authenticated GET/PUT /api/davey/progression with existing session/CSRF/Origin protection; include safe progression status in workspace and paired worker state.
- [ ] Run tests and commit.

## Task 3: Make personalization effective with customer consent

Modify worker/processor.py, server/analysis.py, server/analysis_api.py, server/publication_api.py; tests/test_personal_memory.py, tests/test_davey_personalization.py.
Interfaces: worker state exposes current consent/revision; each worker analyze request can include bounded personalPreferences and its consent revision. Server rechecks current consent before dispatch. The current stored focus/avoid enums become selectionPreferences in validated analysis context.
- [ ] Red tests: default/off/revoked never export; opted-in confirmed owned memory exports only summary; account/device changes clear binding; notes never exported; malicious labels/oversized counts/revision mismatch rejected before paid dispatch; focus/avoid validated and present in actual fake-provider prompt.
- [ ] Preserve exactly-once caching and cost ceiling; no extra paid dispatch for a preference update. Replace legacy beta-only summary permission with separate current customer consent while keeping old default behavior private.
- [ ] Add structured automation safety metadata to new model output; old cached/manual candidates without it remain valid for manual review and ineligible for automation. No tools/actions are enabled. Reject invalid metadata locally.
- [ ] Run relevant privacy, parser, structured-output and exactly-once suites and commit.

## Task 4: Commit predictions and evaluate real manual outcomes

Modify server/analysis_api.py, server/store.py and server/clip_edits.py; add tests/test_davey_validation.py.
Interfaces: Task 2 prediction/evaluate functions. Predictions use fixed current minScore and safety hold; store candidate content hash and selection-context key before manual action. Evaluation uses server-owned candidate hash and human review only.
- [ ] Red tests: count only post-prediction decisions at >=100 prior human decisions with shadow enabled; duplicate edits/reviews cannot create multiple cases; candidate edits invalidate the case; foreign or automatic feedback excluded; current-context statistics meet exact graduation thresholds; no candidate/held safety results cannot auto-approve.
- [ ] Hook manual save inside its existing transaction, preserve signed local feedback receipts and re-review behavior. Mark auto actor separately and exclude it from human counts.
- [ ] Run tests and commit.

## Task 5: Revocable automatic dispatch through existing broker

Create server/davey_automation.py; modify server/publication.py, server/publication_api.py and worker/processor.py; add tests/test_davey_automation.py.
Interfaces: bounded paired-worker POST /api/worker/davey-dispatch, DaveyAutomation(store,pub).dispatch(uid,device_token), authorization checks inside reserve/grant/final-publish. Tag automatic attempts with policy revision, selected destination identity and session/run revision in durable publication metadata.
- [ ] Red tests: final eligibility + explicit rights/automatic consent + independent release switch required; supported exact selected accounts/sources only; verified 1080x1920 captioned artifact and current owned lease; active plan and per-customer/global limits; Stop/revoke/downgrade/account change at every boundary; concurrent duplicate prevention and unknown provider outcomes never blindly retried.
- [ ] Reuse existing server artifact/preview verification and same rendered bytes. Never overwrite a human rejection. Automatic approval is distinct in review history and does not teach/validate itself.
- [ ] Keep network preparation outside SQLite transactions, bounded attempts per tick and durable atomic reservation. Recheck before upload grant and publish finalization. Fail to manual review on uncertainty; log bounded stage/reason metadata, never secrets/raw feedback.
- [ ] Fake-provider lifecycle tests including cancellation and restart; no actual social posts. Commit.

## Task 6: Working phase controls in Streamers

Modify frontend/js/views/davey.js, frontend/js/views/streamers.js, frontend/js/controllers/scouts-controller.js, frontend/js/stream-settings.js and relevant tests; add frontend/js/davey/progression.js as needed.
Interfaces: server-provided workspace.davey status is authoritative. Existing single Save clip settings persists Davey progression settings with clear partial-save feedback.
- [ ] Red browser tests: show phase/meaning from server; no accuracy claim from count; consent visible from beginning; shadow controls hidden before phase 3; automation controls hidden before phase 4; failed/locked save cannot appear enabled; source/destination/cap/score values bounded and safely escaped; pause/revoke available once enabled.
- [ ] Show what adaptation actually used, validation counts/agreement/precision and next criteria. No raw note export or automatic enabling on graduation. TikTok clearly remains user-confirmed.
- [ ] Test refresh/navigation/account-switch behavior and old-server responses default to manual/off. Commit.

## Task 7: Whole-feature security and acceptance

- [ ] Run complete Python and browser suites plus current locked-dependency advisory checks and targeted static review of new process/network/database boundaries.
- [ ] Exercise synthetic customer journey from manual teaching through held-out graduation, opt-in, one fake-provider automatic post and immediate revocation; repeat across separate accounts and plan limits.
- [ ] Fresh whole-branch review, one TDD fix pass for material findings; preserve audit/ledger evidence and screenshots.
- [ ] Keep real provider, signed installer, clean Windows, final deployed security audit and public release gates separate and closed until accepted. Record remaining blockers accurately.
