# Updating ClipBot safely

The full frontend and backend can run locally without changing the live website.
From an isolated checkout, run `python -m ops.local_staging` using the project's
Python environment. Open http://127.0.0.1:8766 and use the local development sign-in.
Stop the preview with Ctrl+C. Its database is `.staging/clipbot.db`; it never reads
the production database or inherits provider secrets. It binds only to loopback.

This preview supports UI, authentication and backend development. Paid AI, real
email, OAuth credentials and billing are intentionally absent. Existing automated
sandbox lifecycle tests cover those integrations; a remote staging deployment with
its own callback addresses and sandbox credentials is the next level of testing.
Do not copy production keys or customer records into a staging environment.

Use a feature branch, review the local preview, run the relevant tests and full
release checks, then promote the exact tested commit through a manual deployment.
Back up before schema changes, check recovery, and retain the previous release for
rollback. Production remains on manual deployment. This local preview adds no
hosting subscription or service cost.
