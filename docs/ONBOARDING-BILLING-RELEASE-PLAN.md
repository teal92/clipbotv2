# Production onboarding and billing release

User scope: guided companion installation, account connections, paid plan selection;
Start requires current connected companion and verified payment. Setup guide opens a
new tab immediately left of Start. Custom is recommended; popularity is not fabricated.
Plans appear directly below Billing. A cyan change button opens a centered plan dialog
with renewal dates and explicit payment authorization. Password security guidance opens
on first current-password focus and leaves typed secrets intact.

## Implementation sequence

1. Keep production Stripe credentials in a separate complete namespace. Test shadow
   settings, partial configuration and legacy compatibility. Include names in encrypted
   recovery whitelist. Keep live release switches off.
2. Configure restricted live key, three standard USD/month prices, strict portal,
   selected-event signed webhook. Stage delivery disabled. Privately validate resources
   before activation. Preserve sandbox history and reconcile mode transition explicitly.
3. Custom checkout: validate all four bounded integer quantities on server; persist an
   immutable quote linked to the owned request. Reuse one of sixteen precreated monthly prices ($10–$85 in $5 steps) for the
   designated Custom product. Keep application price access read-only. Verify product, mode, amount,
   interval, quantity and paid invoice on every webhook/renewal before activating limits.
   Never use browser totals or provider metadata as authoritative capacity. Plan changes
   need immutable old/new quotes and prorated paid upgrades/renewal downgrades.
4. Add onboarding state and semantic dialogs; use actual authenticated worker readiness
   rather than download clicks. Guide connections before plan selection; allow one
   monitoring platform. Persist only nonsensitive dismissal state per account, and
   re-evaluate genuine prerequisites on every Start. Backend remains authoritative.
5. Move plans above change controls. Hide unavailable purchase actions when live billing
   is disabled instead of suggesting real billing is active. Preserve mode validation
   internally. Add password security dialog without collecting extra password copies.
6. Staging: isolated deployment/database, test Stripe, separate OAuth credentials/callbacks,
   email recipient allowlist, no customer records, no production keys, no paid Claude by
   default. Prefer local full-stack staging for the free budget, then a protected remote
   preview only after checking provider free-tier availability. Promote exact tested commit
   and run migration/recovery checks; never copy production environment into staging.

## Acceptance

- Quote tampering, booleans/floats/unknown keys, stale quote and currency/interval mismatch.
- Unpaid, duplicated, reordered or cross-account webhooks; canceled/past-due renewals.
- No duplicate checkout on retries; no plan change without explicit confirmation.
- Fresh companion/version/paid coverage gating, direct API bypass, zero-scout Custom.
- First login, returning paid user, OAuth return, storage denied and multiple accounts.
- Dialog centering, keyboard focus/Escape, password content preserved, mobile layout.
- Full backend/frontend suites and real sandbox lifecycle before live release.

## Implementation verification — October 14, 2026Implemented server-validated Custom checkout and capacity snapshots, paid upgrades,renewal changes, setup guide, onboarding, account billing dialogs, password guidance,and loopback-only local staging. Sixteen reusable monthly prices ($10–$85) are presentin both Stripe catalogs. Catalog access remains read-only on the restricted live key.Security review identified and repaired same-price renewal ambiguity, direct Startprerequisite bypass, and a missing Custom selector. Timeout/canceled scheduling retainsthe old capacity. Same-price changes require a verified owned schedule and target phase.Non-owner Start requires verified email/current policies, a monitoring connection andpaid live coverage. The configured private owner exception remains explicit.Verification: 643 backend tests and 173 frontend tests passed; an additional legitimatelive-customer Start test also passed. Dependency check and whitespace check passed.The encrypted pre-release backup compared all 56 tables with matching content, validforeign keys and integrity. No real charge was made. Actual provider lifecycle acceptance,controlled test-to-live account reconciliation and remaining launch gates still precedeenabling public signup, customer analysis or live charging.
