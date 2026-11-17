# ClipBot billing lifecycle acceptance check

Date: October 13, 2026
Release under test: 6a6dd01
Result: 68 passed in 25.38 seconds; 18 new lifecycle acceptance cases plus 50 related regression cases.

## Isolation

Used the released backend code, temporary local SQLite databases, simulated Stripe provider responses, and synthetic account identities. No live or remote Stripe sandbox subscription was created. No real payment, email, Claude request, social post, customer edit, or production configuration change was made.

The billing, budget, store, publishing and worker code matches the current repository. The billing-period helper differs only in line endings. The initial API-test run stalled during Windows event-loop socket initialization under the sandbox. Its stack trace was captured; running the same tests with local socket access allowed completed successfully.

## Verified

- Verified provider state activates only the intended account through checkout completion, asynchronous payment success, invoice payment, and subscription update events.
- Parallel duplicate webhook deliveries are recorded once and preserve existing spending and review counts.
- A paid renewal grants a new billing-period allowance, preserves historical usage, and blocks further paid work before the new period is verified.
- Past-due, unpaid, incomplete, incomplete-expired, canceled and paused subscriptions deny new paid work. Previously started work can still settle its accounting.
- Scheduled cancellation retains already paid access until the exact period boundary.
- Payment recovery restores access; a delayed failed-payment notification cannot override current verified paid provider state.
- A provider timeout causes no partial entitlement write and permits a later retry of the event.
- A canceled subscription followed by a new lower-plan checkout cannot be overwritten by events from an older subscription.
- Live-mode events are rejected by the sandbox-only adapter.
- Existing regression checks passed for signatures, tier quantities, billing period limits, expiry, capture limits, midnight posting authorization, downgrades and account isolation.

## Production gaps confirmed

The current adapter does not support changing the price on an existing subscription as a customer plan-switch flow. It binds entitlements to the original verified checkout plan and blocks access on a price mismatch. Production needs a deliberate upgrade/downgrade flow with verified prices, proration decisions, allowance treatment and customer-facing status.

This check does not prove end-to-end Stripe delivery, real sandbox checkout/payment interaction, customer portal cancellation, refunds, or live-mode operation. These remain separate acceptance steps. Live billing remains disabled.
