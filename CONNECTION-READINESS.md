# Companion controls update - 2026-10-11

Website Start/Stop and authenticated running/readiness status are implemented. A windowless Windows tray companion and per-user installer are built for owner acceptance. No command-line customer setup is required. Public installer hosting, signing, and corresponding-source/license completeness remain release gates; no public binary is published. See LIVE-PIPELINE-TEST.md.

# Current private acceptance status - 2026-10-11

Hosted owner accounts are connected. Live scout discovery, bounded local capture/transcription/rendering, bounded Haiku analysis, account-owned queue/review, direct social uploads, and verified publication receipts are implemented. Private live acceptance still needs deployment and worker pairing; no live end-to-end result is claimed. See [LIVE-PIPELINE-TEST.md](LIVE-PIPELINE-TEST.md).

Public launch gates remain: managed database/load testing, account verification/recovery and owner hardening, backup/restore, and provider app approval where required. Existing OAuth configuration and encrypted tokens are preserved.

The following notes are historical and describe earlier implementation stages.

---

# Current authorization status (2026-10-11)

OAuth handlers now exist for Twitch, Kick, TikTok, Instagram and Facebook. Tokens are encrypted per user; states are single-use, session/cookie-bound and expire after ten minutes. Account guide selection never grants permissions. Destination selection, local disconnect/provider revocation attempts and non-Meta token renewal are implemented. Missing encryption or app credentials leaves the affected platform unavailable.

See OAUTH-SETUP.md for exact Render variables and redirect URLs. Automated mocked-provider tests are complete; actual platform sign-in needs owner configuration and live testing. Publishing, monitoring, worker uploads and Claude dispatch are still separate unfinished gates. The older inventory below describes the pre-implementation state and is retained as reference only.

# Connections and full pipeline readiness

Connect Accounts is the sole account/worker/service setup view. Normal customers authorize ClipBot with their own platform login; they do not create developer apps or supply client secrets. Personal/creator and developer/test selection changes guidance, never account privileges.

Verified in current code: authenticated session/CSRF checks, worker pairing and revocation, service diagnostics, availability endpoint, account-type allowlist, sidebar grouping. No OAuth handler, encrypted credential store, refresh token flow, or upload implementation is present. All social authorization readiness is false. Platform availability checks make no remote calls and no paid AI calls.

Before connecting owner's permanent test accounts:
1. Review the existing v1 ClipBot apps for Twitch, Kick, TikTok and Meta: client/app IDs, supported login flow, approved scopes, test roles and current redirect URLs. Secrets belong in Render only; do not paste into chat or frontend. Preserve any still-used v1 callback URLs.
2. Implement v2 authorization callbacks with user-bound, expiring, single-use state; PKCE where supported/required; exact callback allowlist; encrypted token storage and refresh/revocation; sanitized server logs; account isolation. Configure the exact v2 callbacks only after implementation and testing.
3. Test connections using the owner's normal/test accounts. Developer-account status is not a substitute for app approval. Token refresh preserves the connection only while authorization remains valid; users may revoke it at the platform.
4. Implement the local monitoring/transcription/rendering worker, bounded Haiku candidate analysis and platform upload handlers; transfer media directly from the local worker. Social availability must account for eligible account types.
5. Test collect -> detect -> analyze -> approve -> edit/render -> upload, including duplicate retries, spend stops, expired authorization, disconnects, and verified receipts.
6. Production database migration, email verification/recovery, owner hardening and public multiuser tests remain separate gates. Successful pipeline tests alone do not finish those account safeguards.

Official references:
- Twitch registration: https://dev.twitch.tv/docs/authentication/register-app/
- Kick OAuth: https://github.com/KickEngineering/KickDevDocs/blob/main/getting-started/generating-tokens-oauth2-flow.md
- TikTok Direct Post approval/test restrictions: https://developers.tiktok.com/docs/en/content-posting-api-get-started
- Instagram account eligibility: https://developers.facebook.com/docs/instagram-platform/instagram-api-with-instagram-login/


## Existing v1 integration inventory (read-only inspection, 2026-10-11)
Source folders: the original local source folders. No files changed in either folder.

Launcher setup_manager.py stores configuration under the ClipBot service in Windows Credential Manager. Read only the public app IDs and callback setting; no client secrets or user access tokens were read.
- Twitch client ID: your-twitch-client-id
- Kick client ID: your-kick-client-id
- Meta app ID: your-meta-app-id
- TikTok client key (public application identifier): your-tiktok-client-key
- Stored META_REDIRECT_URI was not configured.
- v1 TikTok callback is built from CLIPBOT_PUBLIC_BASE_URL (default http://127.0.0.1:8000) plus /api/scout/publishing/oauth/tiktok/callback. Do not replace any existing app callback until v2 handlers are implemented and tested.
- Production .env app entries are blank; config.json and secrets.json are empty. Active app references are in the launcher's protected configuration instead.

Reusable v1 references:
- publishing/oauth.py: TikTok authorization/token refresh; Meta authorization and asset discovery.
- publishing/token_store.py: Windows-protected local storage. It stores records by platform, not SaaS account; do not migrate this store or login tokens to a shared service.
- app/scout/twitch.py and app/scout/kick.py: service app authentication and source scouting.
- app/scout/recorder.py and rolling_capture.py: local capture.
- app/transcriber.py, clipper.py, formatter.py and clip_editor.py: local processing references.
- app/uploaders and publishing/worker.py: platform publishing references.

Adaptation requirements: user-bound persistent OAuth state, isolated encrypted provider credentials, official current scope and PKCE requirements, HTTPS callbacks, refresh/revocation, per-account destination selection, and local worker delivery. Keep v1 installation intact. Existing app IDs do not prove current app approval or user permissions. Windows-protected storage cannot simply be copied to Linux Render. All v2 social authorization still reports unavailable until this adaptation is complete.
