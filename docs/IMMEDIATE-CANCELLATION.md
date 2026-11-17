# Immediate cancellation policy

New customer cancellations end ClipBot access immediately and stop subscription renewal. The customer must explicitly acknowledge loss of remaining paid time and included allowance. Cancellation does not automatically issue a refund or create a proration credit; mandatory legal rights remain. This notice appears before purchasing/changing a plan, in billing controls, and in the versioned downloadable Terms.

The Stripe subscription cancellation uses invoice_now=false and prorate=false. If a verified owned plan-change schedule controls the subscription, its cancellation ends both the schedule and associated subscription. Foreign or malformed schedules fail before mutation. No live customer subscription was canceled by the agent to test this change.

A subscription-specific, mode-bound access revocation is committed with the cancellation request before the only Stripe mutation. It blocks new AI reservations, capture/scout access, worker continuation/resume, upload grants and server-side publication finalization. Monitoring is stopped. Failure receipts and cost settlement remain available so existing spending is accounted for. A timeout leaves a visible reconciliation state; it does not issue another mutation or claim renewal was canceled. The existing authenticated billing refresh and signed webhook can reconcile the provider's current state. Pending owned plan changes become canceled after terminal confirmation. Historical usage is preserved.

The revocation belongs to the canceled subscription, so it does not block a later independently paid subscription. Account login and billing remain available. Canceling does not require accepting newly changed terms; session ownership, CSRF and an explicit strict boolean acknowledgment protect the cancellation route. Refunds and new financial actions remain separate. The companion cannot obtain further server authorization after cancellation. A request or upload already sent to a third-party platform cannot be recalled by changing local billing state.

Earlier cancellations accepted under the paid-through-period policy retain their previously accepted access-end dates. Existing records are not migrated into immediate revocations. In particular, the October 15 live Starter acceptance transaction remains canceled for renewal with its original November 15 access boundary. Ordinary paid expiry retains its established already-authorized-work behavior; explicit cancellation is separately enforced.

Stripe's ClipBot live portal must use cancellation mode immediately and proration_behavior=none. Backend portal validation rejects other configurations. No key scope, price, usage limit, AI budget, tax setting or automatic refund configuration is expanded by this change. Public signup, customer AI dispatch and companion release keep their existing launch gates.

## Verification

Real Stripe sandbox acceptance exercised immediate cancellation of both an ordinary paid test subscription and a schedule-controlled test subscription, with final source hashes recorded in evidence. Both became canceled immediately, lost coverage, handled duplicates safely and reconciled deletion events. Synthetic clock/customer resources were verified and removed. No real charge, production database change or customer email occurred.

The first full audit identified stale policy-version fixtures, an outdated version in the served signup form, and overbroad stopping on natural expiry. These were corrected; an HTTP regression now requires the served signup version to match the backend. A separate worker/publication test proves explicit cancellation blocks existing grants and continuation while failure accounting remains possible. Final audit totals and deployment/configuration evidence accompany the release.

Final full backend audit: 852 tests passed in 262.50 seconds. The final pending-upgrade cancellation adjustment passed the 19-test cancellation/schedule group separately. All 199 frontend tests passed; the cancellation controller check verifies one structured acknowledgment with the session CSRF token. Real Stripe sandbox ordinary and schedule-controlled cancellation checks passed with no real charges or production database writes, and verified cleanup. These totals overlap; they are not added together.

## Live release evidence

Render deployed 6194620be2796433c92ecdddace2f4ccf38fab8f. Read-only checks confirm policy version 2026-10-15.2, matching served signup version, immediate-cancellation purchase disclosure and published Terms, and the new access-revocation schema. Anonymous cancellation receives HTTP 401. The existing restricted live Stripe credential reads the active portal configured for immediate cancellation without proration; uncontrolled subscription updates remain disabled. Public signup, customer AI dispatch and companion public release remain closed.

The earlier live Starter test cancellation was verified unchanged, with no immediate-revocation marker and its original November 15 access boundary. No real customer was canceled, refunded, charged or re-subscribed by the agent during this release. See evidence/2026-10-15-immediate-cancellation-live.json and the source-hash-matched sandbox report.
