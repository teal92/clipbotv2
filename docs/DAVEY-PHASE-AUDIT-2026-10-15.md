# Davey phase and personalization audit — October 15, 2026

Scope: current source, local synthetic tests and official publishing guidance.
No paid model invocation, real social upload, public rollout enablement or
customer-data inspection is part of this audit.

## What customers actually have

The service pins `claude-haiku-5-5` in server/claude_connection.py and calls the
official Anthropic API. All customers use that base model through the owner's
server-held credential and bounded plan/global budgets. Approvals do not create
an individually fine-tuned model or change Claude weights. A later model upgrade
would require a separate validated release, not a feedback-count milestone.

Local feedback is real: per-account/per-service PersonalMemory stores decisions,
allowlisted reasons and notes; only signed, confirmed decisions enter a bounded
200-decision reason summary. Notes stay on customer hardware. This is private
local SQLite protected by the OS account boundary, not an encrypted database.

However, the adaptive loop is not enabled. ClipProcessor._analyze does not send
personalPreferences. An existing regression explicitly checks that it does not.
This matches the documented privacy promise, so exporting a summary must become
an explicit customer choice rather than a silent wiring change. The server
already validates bounded summaries and can include them in analysis context,
but gates them on the older beta-feedback acceptance. Its fallback sees no
reason labels from the current local-only review path. Focus/avoid preferences
are stored but are not supplied to the current analysis context either.

## Phase findings

frontend/js/views/davey.js maps zero decisions to phase 1, 1–99 to phase 2, and
every count at or above 100 to phase 3. Phase 4 is descriptive only and is never
returned by daveyPhase. This is a count display, not measured personalization,
validation, training accuracy or autonomous capability.

Streamers already contains Davey preferences, but approval has only the manual
review option. The server rejects any preference with approval != review.
Automatic clip approval and autonomous publication are not implemented. Hiding
a setting in JavaScript alone would not safely enforce a future phase unlock.

## Existing protections to preserve

An additional launch blocker was reproduced and corrected in source: the
authenticated worker config's analysisEnabled considered only the owner-test
authorization, although the actual analysis endpoint already supports the
protected production customer path. It now reuses that exact customer_enabled
predicate in addition to the existing owner path. The global release switch,
live entitlement, verified email and current-policy checks remain mandatory.
No live switch was enabled. Regression cases cover eligible customers and each
closed identity/payment/release condition, without invoking the model.
The runtime's independent legacy beta gate was also reproduced. A separate
server-computed customerAnalysisEnabled flag now selects the existing production
authorization path; it never sets betaAccepted or grants consent to export
feedback. Old owner-test callers retain their acknowledgment requirement, and
the global analysisEnabled=false still stops both paths. Fake-task runtime tests
exercise actual allocation and heartbeat error behavior without capturing media.

Account-scoped memory and device verification, signed feedback confirmations,
exact local/website origins, preview capabilities, strict bounded JSON, no raw
private notes in cloud prompts, untrusted transcript/feedback handling, exactly
one paid dispatch per job, no tools in the model call, per-plan and global budgets,
required verified mobile artifact, and publication outcome reconciliation.

## Platform boundary

TikTok's current Direct Post documentation requires creator information, user
metadata choices and express upload consent. Its sharing guidelines require
editable preset titles/hashtags and user privacy choices. This audit does not
interpret a broad account opt-in as permission to remove that per-content flow.
Unattended TikTok stays unavailable until a compliant approved flow is established;
the final phase must disclose supported platforms rather than promise all socials.

Primary references:
- https://developers.tiktok.com/docs/en/content-sharing-guidelines
- https://developers.tiktok.com/docs/en/content-posting-api-reference-direct-post

## Required work

Implement customer-consented bounded reason-summary personalization and enforce
focus/avoid settings in reasoning; unify phase authority on the server; add
shadow validation independent of the feedback-count bar; then add explicit,
revocable, account-scoped autonomous publication only after qualification. Each
platform, plan, version, lease, safety and duplicate-prevention check must run at
dispatch time, not only when a customer enables a setting. See the proposed
phase design for the release criteria. None of these planned behaviors is
described as deployed by this audit.
