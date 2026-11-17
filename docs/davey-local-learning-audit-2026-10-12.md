# Davey audit and rollout costs

Verified October 12, 2026. This is an architecture audit and a projection, not a capacity or cost guarantee.

## What the uploaded session showed

The supplied session ran from 01:53:58 to 02:17:01 UTC on October 13 (9:53:58–10:17:01 p.m. New York on October 12). There were 74 new captures and one resumed older job. Its 62 paid reviews produced 40 no-moment outcomes, 14 unreadable-response failures, two invalid-range failures, and six schema-valid candidates. Five candidates scored 38 or 58, below the configured threshold of 60. One scored 62 and generated a review preview. These outcomes must be counted once per job, rather than once per emitted event.

No raw historical provider response was retained, so the exact cause of every old JSON failure cannot be reconstructed. The format correction uses documented structured outputs, handles a single unambiguous JSON response, and continues to reject conflicting objects, duplicate keys, invalid timestamps and unsafe metadata. There is no extra paid retry or automatic score reduction. Non-selection is now separated from technical failure, with bounded score and length diagnostics.

## Where the work runs

| Component | Location | Reason |
|---|---|---|
| Stream capture, rolling buffer and cue detection | Customer companion | Keeps stream bandwidth, media and detection work off ClipBot hosting |
| Whisper transcription, captions, FFmpeg blur/vertical rendering and previews | Customer companion | Uses customer CPU, disk and media files |
| Personal reason labels and written review notes | Account-scoped local SQLite | Private feedback stays on that computer |
| Account identity, selection settings, minimal approval audit, budgets and publishing authorization | ClipBot server on Render | Requires a trusted shared authority |
| Bounded transcript reasoning and scoring | Anthropic Claude API | Claude is hosted by Anthropic, not on the ClipBot server |
| Platform upload work | Customer companion with server-authorized upload grants | Local media remains local until the user authorizes publishing |

Local feedback records are bounded to 2,000; summaries use at most 200 confirmed decisions. Confirmation is tied to the paired device and account. Notes are plain local SQLite under the operating-system account boundary, not an encrypted database. Repeated local reads reuse a short ownership cache; writes still verify ownership. Local-memory summaries are not exported by this release. An optional reason-count export requires separate approval.

New shared-learning collection is paused. Existing shared records are retained; they are pseudonymized, not guaranteed anonymous. Historical server feedback is retained for compatibility; this release does not claim to have migrated or deleted it.

## How close the proposal is

The proposal fits the intended direction: personal memory first, separate opt-in shared learning, validated releases, and revocable publishing permission. It should guide incremental changes rather than a rebuild.

Previously, personal adaptation consisted of allowlisted reason counts from account-scoped server review history added to an analysis prompt. Free-form explanations were excluded. The new foundation records private reasons and notes locally and authenticates confirmation, but it does not train model weights and does not yet apply that local summary to cloud recommendations.

There is no active fine-tuning, global model-update pipeline, quarantined training dataset or benchmark-driven promotion process. The three trust modes exist as a design/prototype; the live workflow still requires manual review and explicit publishing. Focus/avoid preferences are stored but are not yet enforced in the reasoning prompt. Do not describe any of these unfinished capabilities as deployed.

Next steps should be evaluated in this order: optional bounded personal context with consent; observable preference ranking and correction/reset controls; held-out clipping-quality and safety evaluations; then a separate off-by-default contribution flow with provenance, quarantine, retention and human-approved versioned releases. Only consider fine-tuning after evidence justifies its cost.

## Who pays and likely scale

ClipBot uses the owner's server-held Anthropic API credentials. Customers do not currently supply their own Claude keys. Customer plan payments would fund the service, but the current payment integration is still in prelaunch sandbox mode.

The deployed application limits remain **$400 per month and $20 per day**. Per-account plan ceilings are $2/month Starter, $6/month Creator and $12/month Pro, in addition to daily usage presets and review allowances. Starter allows 450 reviews/month and Creator 1,350; Pro has no review-count allowance ceiling but still has spending limits. The active owner live-test authorization is narrower than a customer launch and must not be mistaken for public rollout activation.

The sample's 62 reviews cost **$0.006895** in the live ledger, about $0.000111 per review. At the sample's roughly 161 reviews/hour, four hours/day for 30 days gives approximately:

| Users at the same workload | Claude cost/month before plan review limits |
|---|---:|
| 1 | $2.15 |
| 10 | $21.50 |
| 30 | $64.50 |
| 60 | $129.00 |

Eight hours/day doubles these estimates. These are extrapolations of one short session, not a forecast of customer behavior. They exclude hosting, storage, payment fees and platform services. More transcript/output tokens, more triggers, different models or prices increase cost. At the maximum 8,000 input and 1,000 output tokens currently allowed, a review is roughly $0.0013 before rounding, making the same unconstrained four-hour workload about $25/user/month; application plan and global stops would pause reviews before all that usage could occur.

Current [official Haiku 5.5 pricing](https://platform.claude.com/docs/en/models/haiku-5-5/overview) for these short requests is $0.10/million input tokens and $0.50/million output tokens. [Structured outputs](https://platform.claude.com/docs/en/build-with-claude/structured-outputs) are supported; schema overhead can change measured input usage slightly. Failed paid responses still consume tokens.

The safeguards reserve worst-case cost before dispatch, allow three global and one per-account concurrent analyses, throttle to one at 80% of the monthly ceiling, and do not automatically retry paid failures. Unknown provider outcomes remain reserved pending reconciliation. These controls apply to requests through ClipBot, not unrelated apps sharing the Anthropic account. No server-load claim for 30 customers has been made without a representative load test.
