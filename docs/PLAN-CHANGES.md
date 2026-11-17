# ClipBot plan changes

Scope: standard sandbox Starter, Creator and Pro subscriptions. Live billing remains disabled.

Customers change plans under Account → Plans & Billing. They explicitly authorize the test payment before submitting an upgrade. The interface shows pending payment, applied changes, expired payment, scheduled downgrades and canceled schedules. Refresh Billing Status reads current Stripe state and is limited to once per ten seconds per account.

## Payment and allowance rules

Upgrades replace the existing subscription item with pending_if_incomplete, always_invoice and an unchanged billing anchor. Stripe must confirm a paid invoice and apply the target item before ClipBot grants the new scout/daily limits. An unpaid upgrade retains the previously verified paid plan while the original paid period is valid and unchanged. Expired upgrade invoices clear the pending operation so the customer can try again.

Existing usage, daily posting reservations and AI accounting are retained. The monthly AI allowance increases by the prorated difference between the old and new plans for the remaining billing period. Bounded monthly review increases use the same fraction. A full new monthly allowance starts only at the next verified paid renewal. Multiple upgrades in one period add only their incremental prorated allowance.

Downgrades use a two-phase Stripe subscription schedule. The existing plan remains until the current paid period ends. The next phase uses the lower price, without a mid-period refund or proration. Coverage changes only when the new period and payment are verified. A released/canceled schedule clears the pending downgrade. A customer can request one pending change at a time.

## Security and recovery

The session chooses the customer account; the endpoint accepts only a standard plan name. Origin and CSRF checks apply. Server-side price, amount, currency, monthly interval, quantity, subscription/customer ownership and sandbox mode are checked. An authorized operation is committed before provider requests; repeated requests reuse identical parameters and idempotency keys. Unknown request outcomes older than 23 hours require reconciliation instead of a new automatic charge.

External price edits without a recorded user-authorized change do not provision a different plan. Complex subscriptions with discounts, tax arrangements, trials, transfers or existing schedules require assisted handling rather than silently discarding settings. Hosted payment links accept only HTTPS invoice.stripe.com URLs and are never logged.

## Validation and remaining launch work

Regression checks use simulated providers and temporary databases. Real Stripe sandbox checkout, proration/payment authentication, subscription schedule transitions, and webhook delivery still require end-to-end acceptance. Cancellation/refund UI and live-mode deployment are separate production work.
