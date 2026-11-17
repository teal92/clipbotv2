# ClipBot pre-launch design and implementation plan

Goal: real local accounts, no fictional activity, clean Davey and usage screens, and fail-closed spending controls before public launch. Keep modular vanilla JS and all files inside clipbot-saas. User has authorized implementation in this chat; execute inline.

## Design
FastAPI serves frontend and authenticated APIs on one origin. SQLite stores account/session/preferences and an integer-microdollar usage ledger for single-instance local testing. Public deployment is blocked until managed Postgres migration, verification/recovery email, distributed login rate limits and billing are connected. HTTPS cookies and exact Origin/CSRF checks protect writes. No API key reaches the browser. Signup creates no paid plan or AI allowance.

Davey: one progress card based on recorded feedback, clearly distinct from training a model; preset preferences, review approval and throttling controls stay here. Dashboard and pipeline tabs show actual API counts or clear empty states; no seeded creators, clips, progress or performance. Logs contains Errors and Usage subtabs. Usage displays input/output tokens, reserved/spent cost, plan coverage and daily token activity from server ledger only. Account shows actual identity, plan/coverage and billing status. Landing offers login/signup.

## Implementation tasks and checks
1. Auth backend: server/app.py and server/store.py; tests/test_backend.py checks signup/login/logout, cookies, CSRF, tenant isolation and no default entitlement. Persist hashed passwords and hashed expiring sessions.
2. Budget ledger: server/budgets.py; tests cover atomic simultaneous reservations, global/per-user stops, concurrency, idempotence and settlement. Reject AI jobs by default; no provider calls or retries until enabled through a reviewed adapter. Purchases cannot bypass global stops.
3. UI: frontend/js/service-state.js, views/auth.js/account.js/usage.js and controllers/account-controller.js. Replace sample renderers with empty states; simplify Davey. Test empty output, no imaginary usage, auth and account route.
4. Local integration: install bounded dependencies in project .venv, run both suites and browser account/navigation checks. Add launch checklist and hosting setup. Do not claim public deployment, payment collection or connected Claude.

## Launch gates
Business-wide monthly Claude stop and daily stop, lower per-user spend/review allowances, concurrency, bounded tokens/retries and kill switch; verified paid additions only, no automatic overage. Hosting account, HTTPS/DNS, Postgres durability/backups, mail verification/recovery, Stripe webhook checkout, local worker and social OAuth must pass before public signup.
## Execution record
Tasks 1–4 implemented for local pre-launch:14 backend and35 frontend tests pass. Review corrections:explicit loopback signup, constant password verification work, best-effort legacy cache cleanup, persistent cost-overrun stop and actual-byte body limit. Provider dispatch/public signup/billing remain closed; deployment is blocked on hosting account and the documented public-launch integrations. No external resources provisioned.
