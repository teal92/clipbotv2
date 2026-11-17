# Davey, Logs, and Settings implementation plan — 2026-10-10

Goal: finish the three frontend workspaces with real local state and a defined Claude backend handoff, preserving modular vanilla JS.
Execution: inline, within clipbot-saas; no dependencies or downloads.

Security: no API keys or OAuth secrets in forms/storage; escape untrusted content; budgets are pending server-enforced limits; review is the only supported automation mode.
Efficiency: one delegated controller, bounded 200-event/200-feedback stores, no automatic AI requests or background polling.
Regression risks: review submission and router integration; new styles scoped to new tabs; retain old module exports and routes.
Tests: corrupt/unavailable storage, validation boundaries, malicious text, duplicate reviews, redaction, bounded retention, offline/malformed service responses, navigation and handler counts.

1. Implement validated settings-state.js, activity.js, davey/learning.js, and runtime.js with same-origin status checking.
2. Add views/davey.js, views/logs.js, views/settings.js and controllers/workspace-controller.js. Save preferences, feedback, and budgets; search/filter/clear logs; manually check service health. Clearly mark offline functions.
3. Wire app.js and Clips review submission to saved feedback and activity. Add route and controller regression tests.
4. Run all Node tests and syntax checks, inspect browser UI if available, document API contract and public launch blockers in PRODUCTION-READINESS.md.

Public launch: separate authenticated multi-user backend and worker are required; local drafts/logs are not a tenant database. No claim of production readiness from UI completion.
