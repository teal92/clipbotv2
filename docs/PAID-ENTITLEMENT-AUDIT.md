# Paid entitlement enforcement audit

Operator: YOUR COMPANY NAME
Assessment: October 13, 2026
Scope: verified plan quantities, server/worker/publishing boundaries, UTC daily limits and paid billing-period review/spending limits. No real charge, customer reset or social post was created during testing.

## Current standard-plan contract

| Plan | Standard price/month | Scouts shared across Twitch + Kick | Favorites / categories | Reviews/day | Reviews/paid billing period | AI allowance/paid billing period | Unique clips/new upload grants per UTC day |
|---|---:|---:|---:|---:|---:|---:|---:|
| Starter | $7 | 6 | 0 / 0 | 15 | 450 | $2 | 20 |
| Creator | $25 | 12 | 3 / 3 | 45 | 1,350 | $6 | 20 |
| Pro | $60 | 30 | 10 / 10 | No fixed advertised count | No fixed advertised count | $12 | No fixed plan count |

Pro remains subject to AI spending, concurrency, capture, upload-size and platform safeguards. No plan overrides the existing business-wide $400/month and $20/day stops. Daily spending presets can stop reviews sooner. A cap is an allowance ceiling, not a promise of that many usable clips or successful posts. Publishing counts reservations/new upload authorizations; external platform delivery may occur later. Cross-posts consume one daily unique-clip slot and each clip/destination pair has one publication attempt. Unknown provider outcomes are not retried automatically.

A $5 verified-Patreon Starter proposal exists, but the current standard billing path charges $7. Custom proposals and discounted offers do not activate coverage; their verified purchase/verification paths remain production work. Do not advertise them as completed paid flows.

## Confirmed repairs

- Outstanding AI reservations must still have active, unexpired authorization before further paid work. Historical settlement and completed records remain available.
- Coverage, billing plan and expiry are projected from one database snapshot so a plan change cannot combine Starter scout limits with Pro publishing treatment.
- Paid queued captures and new capturing transitions stop on inactive/expired coverage, zero scouts or stopped monitoring. Already captured local work and accounting remain usable.
- New upload grants recheck active coverage and reserve current UTC-day clip capacity, closing a prepared-before-midnight carryover bypass.
- Same-day reservations from Pro cannot authorize new uploads after a downgrade below the current daily allowance. Already granted work may finish and retain receipts.
- A publishing reconnect cannot silently change the identity used to finish a prepared upload.
- Paid webhook reconciliation verifies the expected price, amount, currency, quantity, monthly recurrence and test/live mode before provisioning.
- Paid monthly review and AI allowance counts follow the provider-verified subscription period, rather than refilling at a UTC calendar-month boundary. Each new reservation records its timestamp in the same transaction. Historical jobs without precise timestamps are conservatively counted for overlapping days. Missing or mismatched paid dates stop further AI dispatch pending reconciliation.
- The existing active test subscription's period was privately checked against Stripe and preserved. Its coverage was not changed and no charge was made.

## Verification focus

Tier matrix; inactive/expired/revoked coverage; forged webhook; wrong price or recurrence; quotes not provisioning; account isolation; combined scout allocation; parallel claims; independent daily/monthly review and microdollar caps; month crossing; late settlement; midnight upload grants; downgrades; reconnect identity and uncertain provider outcomes.

## Global C2 metrics

Metrics read all ClipBot customer accounts. Davey contribution totals and period charts count received shared_feedback records, never local personal notes. Shared collection remains paused; the UI shows that state instead of inventing training progress. The horizontal bar uses the existing 1,000-contribution evidence milestone. Day/week/month/year charts use 24 hourly, 7 daily, 30 daily and 12 monthly UTC buckets. Contribution count is not model accuracy or a claim of retraining.

## Still required for paid production

Live/test data isolation and live billing credentials/products; safe live-mode adapter; billing portal/cancellation and refunds; verified public signup/email recovery; explicit acceptance of current terms; opt-in shared-contribution collection if desired; provider approvals; installer signing; capacity/restore/security/legal release acceptance. Current Stripe integration remains sandbox-only.

References: https://docs.stripe.com/billing/subscriptions/webhooks and https://developers.tiktok.com/docs/en/content-posting-api-get-started
