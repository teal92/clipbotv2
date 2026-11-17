# Stripe sandbox setup

This increment only supports Starter $7, Creator $25 and Pro $60 monthly TEST subscriptions. Live keys and live payment events are refused. Custom plans, Patreon verification, add-ons, portal, refund/dispute handling and live production billing remain launch blockers.

## Hosting environment
In Render > clipbot-prelaunch > Environment, set:
- STRIPE_SECRET_KEY: your sandbox secret key (sk_test_...). Enter it directly in Render; do not paste into chat or commit it.
- STRIPE_PRICE_STARTER: price_...your-price-id
- STRIPE_PRICE_CREATOR: price_...your-price-id
- STRIPE_PRICE_PRO: price_...your-price-id
- STRIPE_WEBHOOK_SECRET: endpoint signing secret (whsec_...), from the sandbox event destination below. Enter directly in Render.

Checkout stays disabled until secrets and all three price IDs exist. .env.example is a reference, not automatically loaded. Never change public signup or development bypass flags to test payments on the public service.

## Event destination
Create a sandbox webhook event destination for:
https://clipbot.your-domain.example/api/billing/webhook
Use snapshot events for your Stripe account. Select:
- checkout.session.completed
- checkout.session.async_payment_succeeded
- customer.subscription.created
- customer.subscription.updated
- customer.subscription.deleted
- customer.subscription.paused
- customer.subscription.resumed
- invoice.paid
- invoice.payment_failed

Copy its signing secret directly into Render. Synthetic dashboard events not linked to a ClipBot checkout are acknowledged but do not create account coverage.

## Verification
An authenticated ClipBot account is required. Public account creation remains closed, so first perform local sandbox tests or provision a private test account through a reviewed operator flow. Open Settings > Plans & Billing > Test Starter Checkout. Use only Stripe's documented sandbox payment methods. After return, open Account or refresh Usage to load verified coverage. Confirm webhook delivery, duplicate-event idempotence, cancellation, expiry, payment failure and unchanged budget ledger. Subscriptions grant coverage only while active with a paid latest invoice and unexpired period. No Claude dispatch is enabled by a subscription.

Security references:
https://docs.stripe.com/billing/subscriptions/webhooks
https://docs.stripe.com/events/manage-webhook-endpoints

Pending sessions reuse the same stored checkout request for 24 hours, matching Stripe default expiry. Changing plans during a pending checkout is blocked. Production must add explicit session expiration/reconciliation and test uncertain-network-result recovery before accepting real payments.

For hosted network diagnosis, Render > service > Shell: run `python -m server.network_check`. It checks key formatting and retrieves the Starter price only. It never creates payments, disables TLS verification, prints API keys or prints exception messages. Share only its diagnostic output.

## Private hosted test account
In Render > service > Shell, run `python -m server.operator create-test-account`. It uses CLIPBOT_DB_PATH, requires an existing service database, sandbox key and disabled signup/bypass flags. Enter your email, display name and password directly in the interactive Shell. Password input is hidden, never supplied as a command argument. It creates a normal account with no admin privileges or coverage and refuses duplicates. Sign in at the custom ClipBot domain, then use the sandbox checkout buttons. This operator command is not an HTTP endpoint and does not open public registration.

Checkout uses Dashboard-managed dynamic payment methods; payment_method_types is omitted for the current Stripe API. Corrected v2 requests use a versioned idempotency key to avoid replaying the previous unsupported-parameter rejection. Saved successful checkout sessions are still reused.
