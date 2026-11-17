# ClipBot pre-launch operator tools

These commands run from clipbot-saas on the host. They are not available to customer accounts and require access to the host filesystem. They print customer-submitted text as JSON, never execute it, and do not send it elsewhere.

Read the latest reports:
```
.\.venv\Scripts\python.exe -m server.operator reports --limit 50
```

Create a verified SQLite backup inside this project:
```
.\.venv\Scripts\python.exe -m server.operator backup server/data/clipbot-backup.db
```

Restore into a NEW file (never replaces a running database):
```
.\.venv\Scripts\python.exe -m server.operator --database server/data/clipbot-backup.db restore server/data/clipbot-restored.db
```

Before switching the service to a restored file, stop it, verify the copy, then set CLIPBOT_DB_PATH to the restored absolute path. Existing sessions are included in this private backup. Keep reports and backups restricted to the service operator; database files are ignored by Git. Managed Postgres backups and off-host recovery remain required for public launch.

Quotes: POST /api/billing/quote uses the authenticated session and CSRF token, takes plan and custom quantities only, and returns integer cents. It never buys a plan or enables Claude. Patreon discount eligibility is internal-only pending verified integration.

## Local worker connection test

In Connect Accounts, generate a pairing code. In a separate PowerShell terminal within clipbot-saas, run:
```
.\.venv\Scripts\python.exe -m worker.client
```
Enter the code at the hidden prompt. The worker sends a heartbeat every 30 seconds; Ctrl+C stops it. The credential stays in memory only, so restart requires another pairing code. Connect Accounts > Disconnect Worker revokes it. Remote service addresses must use HTTPS. This connection test does not yet monitor, transcribe, render or upload media.

Private copies must remain under server/data when using the CLI. The frontend directory is publicly served and is forbidden as a backup/restore destination.


## Claude connection check (no prompt or token generation)
After deploying the official SDK and setting ANTHROPIC_API_KEY in Render, run `python -m server.claude_connection` in the service Shell. It reads Claude Haiku 5.5 model metadata with a 10-second timeout and zero retries. Only readiness, model ID, and sanitized error categories/status are printed. No credentials or provider response bodies are printed. `dispatchEnabled: false` is expected: adding funding or a key does not start AI requests. Budget-backed candidate dispatch remains a separate implementation and verification step.


## Owner-only metrics
Deploy the metrics update, then run this in Render Shell: `python -m server.admin --owner-email support@your-domain.example`. It prints the existing account ID only and does not grant access. In Render Environment add `CLIPBOT_ADMIN_USER_ID` with that returned ID, save/redeploy, then sign in with the owner account and open `https://clipbot.your-domain.example/admin`. The Owner Metrics navigation appears only for this account; every metrics API request checks the same account ID server-side. Missing configuration denies all admin access. Local development bypass accounts cannot become admin. The owner page is read-only and contains aggregate counts, no keys, customer identities, revenue or billing details. Protect the owner account; MFA and optional Cloudflare Access are future hardening work. A separate subdomain is unnecessary for this version.

Recently active users means signed-in browser presence within two minutes, refreshed every 30 seconds while visible; connected workers means valid heartbeats within 90 seconds. Admin polling runs every 15 seconds while visible and stops when navigating away. Token totals are recorded settled requests, not a provider-wide billing report. Publishing totals remain unavailable/zero until verified local publishing receipts are implemented; no counts are inferred from approvals.

## Required beta feedback contribution
Users must acknowledge beta-feedback-v1 in Davey before submitting new clip decisions. There is no opt-out during beta. The shared pool stores a deduplication fingerprint, approve/reject decision, listed reason labels and update timestamp. No raw media, transcript, titles, written explanations, email or account ID are copied into it. Fingerprints are pseudonymous, not a promise of irreversible anonymization; retained personal feedback remains account-scoped. Existing decisions are not retroactively contributed. A privacy notice and retention/deletion workflow must be finalized before public beta. Shared analysis, validated rule/prompt updates and rollback are not enabled by this change.
