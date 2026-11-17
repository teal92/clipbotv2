# Proposed Davey progression and autonomous posting

Status: owner approved the measured graduation gates on October 15, 2026.
No new autonomous permission or model call is enabled by this document.
User goal: Davey should adapt to each customer's
preferences, unlock working capabilities as it progresses, and eventually post
eligible clips automatically under that customer's chosen controls.

## Personalization contract

Keep the shared base Claude model. Offer a separate, clear customer choice in
Streamers → Davey: allow bounded reason-count summaries to be used for personal
clip selection. Explain exactly what leaves the computer: listed reason labels
and counts from up to 200 confirmed reviews, never written notes or raw feedback
files. Keep participation in global learning separate and off. Turning personal
context off stops future export; reset clears the account-bound local preference
memory after explicit confirmation. Existing manual review remains usable.

Treat summary fields as untrusted bounded data. Reverify the paired account and
the current consent revision before each analysis. Apply saved focus/avoid
preferences as validated enums. Keep the same paid dispatch limits and exactly-once
ledger. Do not upload files, run code, install packages or give Claude publishing
credentials. No claim of fine-tuning or guaranteed model accuracy.

## Proposed phase criteria

1. **Getting started:** no confirmed manual decisions. Preferences and manual
   approval are available; explain how to teach Davey.
2. **Learning your preferences:** 1–99 confirmed manual decisions. With consent,
   bounded reason summaries influence new reviews immediately. Show the number
   of confirmed decisions and whether personal context was actually used.
3. **Proving its choices:** at least 100 confirmed manual decisions. Show Davey's
   proposed approval/rejection before the customer decides. Evaluate at least
   25 new, distinct, manually reviewed clips whose predictions were committed
   before the human decision; never validate on the same feedback used to build
   their context. Count only current policy/model/preferences revisions.
4. **Autonomous posting available:** require at least 90% agreement across those
   validation decisions, at least 20 predicted approvals with at least 95% human
   approval precision, and no unresolved safety or publishing incidents. These
   are conservative initial product gates, not a statistical accuracy guarantee.
   Unlock controls; do not enable them automatically.

The server owns phase, qualification and settings. Duplicate reviews, repeated
edits, browser state and forged worker summaries cannot advance qualification.
Automatic decisions never count as human teaching or validation. Context/model
changes invalidate obsolete validation evidence; explicit opt-in must be renewed
if the authorized publishing policy changes materially. A revoke, serious safety
issue or lost eligibility returns queued content to manual review.

Validation is prequential: each prediction is committed before that clip's human
decision. Earlier confirmed feedback can inform later predictions. Routine new
feedback does not reset the evaluation round; material focus/safety/score/source
setting changes or model/policy revisions do. Written notes remain local.

## Streamers controls

Keep everything in the existing Davey section. Show personal-context consent,
content focus, safety preferences and activity. Reveal shadow-validation controls
in phase 3. Reveal autonomous-post controls only when phase 4 is genuinely
qualified. Offer: an off-by-default enable switch, supported destination accounts,
daily cap limited by the paid plan, minimum selection score, approved content
sources, and a pause control. Explain why unavailable platforms cannot be selected.
Keep a visible status and audit trail once enabled. Existing settings are
authorized and validated server-side even if hidden fields are forged.

## Publication boundaries

Reuse the existing durable publication broker and customer-side renderer/uploader.
Only a verified final captioned artifact can become an automatic candidate. Scope
the grant to the customer, exact destination account, artifact and policy revision.
Check current paid access, posting allowance, consent, phase eligibility, platform
permissions, destination identity, worker lease, safety and deduplication immediately
before dispatch. Stop global ClipBot → stop automatic dispatch as well. No charge
or post retry when the previous provider outcome is unknown; reconcile first.

Instagram/Facebook may be included only after their real acceptance checks pass.
TikTok remains in its required user-confirmed flow unless a separately verified
approved integration permits the proposed unattended behavior. Provider policies
are capabilities, not UI switches to bypass. AI cannot create or expand its own
authorization. Sensitive/uncertain clips remain in manual review regardless of score.

## Required acceptance

Prove phase boundaries and rollback; first-consent/off/revoked/reset behavior;
account/service/device isolation; summary bounds, prompt injection and forbidden
files; focus/safety enforcement; held-out evaluation with duplicate/edit resistance;
current-revision qualification; forged hidden controls; plan/daily/concurrency limits;
destination changes, revoked tokens and worker loss; final-artifact verification;
stop during dispatch; confirmed/pending/failed receipts and unknown-outcome recovery.
Use fake provider clients and synthetic media first, then separately authorized
real account/provider acceptance. Live automation stays off until that passes.
