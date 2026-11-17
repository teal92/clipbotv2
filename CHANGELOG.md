# ClipBot beta changes

## 0.2.10 — favorites and trigger safeguards

- Add Account → Patch notes with persistent release history shared with the update popup.
- Rename forced priorities to Favorite streamers and Favorite categories. Add them separately in each Twitch/Kick card, including offline streamers, with removable saved lists.
- Use gold text for favorites and white text for ordinary scouts. Remove special scout borders/backgrounds and describe active scouts as monitoring.
- Preserve unfinished favorite entries during refreshes and keep prior saved preferences visible and removable.
- Keep ordinary stream discovery available while favorite categories are offline, respecting existing explicit category filters.
- Require valid trigger settings in the production companion. Missing settings pause scouting instead of falling back to repeated timed capture/review. Quiet rolling-buffer footage does not create AI review jobs; configured cues or manual Clip now create clips with saved before/after timing.
- Keep existing public showcase assets out of the sensitive API request bucket without changing API quotas.

The companion patch updates 0.2.9 to 0.2.10. Existing account isolation, plan limits, $20/day and $400/month shared Claude stops, unsigned-beta disclosure and artifact acknowledgement remain enforced. Installer and hosted-artifact acceptance are recorded separately before public promotion.

## 0.2.9 — analysis reliability patch

- Show an automatic companion update notice on a new visit/refresh or return to a visible tab when a connected companion needs an available update. Include readable patch notes; defer behind other dialogs and suppress repeat prompts during the visit.
- Add comma-separated Bulk phrases entry with editable rows and the existing rule limits.
- Separate discovery and analysis request allowances so normal discovery refreshes cannot consume the analysis request bucket.
- Preserve safe, specific HTTP failure codes in companion session logs instead of hiding them behind a generic processing error. Do not include provider bodies, credentials, transcripts or chat text.
- Ask Davey for an explicit supported clip duration, preserve fractional timestamp boundaries, and skip impossible capture-length requests before spending provider credits. Existing scoring and safety rules remain in force.
- Accept documented numeric-string Kick token lifetimes with strict bounds and a one-day cache ceiling.
- Label companion upgrades as beta patches and record their previous version, source commit, size and SHA-256 hash. Keep account pairing and local data during an update.
- Add SQL injection attack regression tests for login, reports, stored clip metadata and Davey feedback, including account isolation.

Shared Claude caps remain $20/day and $400/month. No automatic paid retries or plan allowance increases are introduced.

An installer is not approved for public promotion merely because it builds. The new artifact must pass frozen-runtime checks and actual install/update and pairing acceptance. Unsigned beta disclosure and per-artifact acknowledgement remain required.
