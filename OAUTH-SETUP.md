# One-time owner setup for platform sign-in

Customers use Connect Accounts -> platform -> account guide -> Continue to Sign In -> approve -> return. Existing accounts are supported; customers never need developer apps or keys. The account type changes guidance only. Instagram uses Facebook Login and requires a professional account linked to a Page; Facebook requires a Page with publishing access. TikTok public Direct Post requires approved scope and audit; test posts remain private until audited.

## First test: Twitch
1. Deploy this OAuth update on Render. The encryption dependency is installed by the build.
2. In the private Render Shell run `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`. Copy the resulting key directly to the Render environment variable CLIPBOT_TOKEN_ENCRYPTION_KEY. Do not put it in chat. Keep a secure backup. Do not regenerate on each deployment; changing it makes existing saved connections unreadable.
3. Add TWITCH_CLIENT_ID=your-twitch-client-id and the existing TWITCH_CLIENT_SECRET directly to Render Environment. Obtain the secret from your existing app settings; do not paste it into chat.
4. In that existing Twitch developer app add https://clipbot.your-domain.example/api/connections/twitch/callback to OAuth Redirect URLs. Preserve existing v1 URLs. Save.
5. Save/redeploy the Render environment. Open the hosted ClipBot and choose Connect Accounts -> Twitch -> your account type -> Continue to Sign In. Sign in on Twitch only if asked and approve. ClipBot should return to Connect Accounts and show the real account name.
6. Verify reload persistence; disconnect removes ClipBot tokens and attempts platform revocation. Test decline once, then connect again. No paid AI or media posting starts through these actions.

## Remaining platforms
Use the same stable encryption key. Add the existing IDs and private secrets in Render. Enter only public values from .env.example automatically; this file is not loaded by Render.

| Platform | Public variable | Private variable | Exact redirect URL |
| --- | --- | --- | --- |
| Kick | KICK_CLIENT_ID=your-kick-client-id | KICK_CLIENT_SECRET | https://clipbot.your-domain.example/api/connections/kick/callback |
| TikTok | TIKTOK_CLIENT_KEY=your-tiktok-client-key | TIKTOK_CLIENT_SECRET | https://clipbot.your-domain.example/api/connections/tiktok/callback |
| Instagram | META_APP_ID=your-meta-app-id | META_APP_SECRET | https://clipbot.your-domain.example/api/connections/instagram/callback |
| Facebook | META_APP_ID=your-meta-app-id | META_APP_SECRET | https://clipbot.your-domain.example/api/connections/facebook/callback |

For Meta add both URLs under Facebook Login Valid OAuth Redirect URIs; keep existing URLs. META_GRAPH_VERSION defaults to v24.0. TikTok adds its URL to Login Kit Web and enables approved user.info.basic and video.publish scopes. Kick requests user:read channel:read with PKCE. Twitch requests no private-email, chat-writing or channel-management scope in this first monitoring connection.

Meta discovers eligible Pages and linked professional Instagram accounts. Both Meta sign-in routes also request business_management for business portfolio access. Directly managed Pages still require only their platform Page/publishing permissions; portfolio consent is not a substitute for eligible Page access. The app must have this permission available to the signing-in user (Standard access for app-role testing; appropriate reviewed access for other customers). ClipBot does not use business-management write endpoints or request advertising permissions. An empty Page list still requires a live retry to confirm whether portfolio consent resolves it. If several are eligible, the user selects one after sign-in. No Page tokens reach the browser. Disconnecting one Meta destination retains the other destination's authorization; the user can remove all ClipBot access in Meta account settings. Meta authorization uses long-lived tokens but must be reauthorized when it expires or is revoked. Twitch/Kick/TikTok support server token renewal with an account-scoped lease; the future worker should invoke renewal before expiry. Current UI offers Renew Connection for expired non-Meta authorization.

## Verification and limits
Automated tests use mocked provider responses, not live credentials. Live app scope/approval/redirect settings must be confirmed with actual sign-in. Readiness means encryption and app credentials are present; it does not prove app approval. Connected means an identity was verified at authorization and locally saved tokens have not expired; provider revocation can invalidate access earlier.

PublishingReady remains false until the local publishing worker and end-to-end upload checks are implemented. Linking an account does not start monitoring, Claude reviews or uploads. No media is sent to the shared server. Public signup remains closed.

Uvicorn access logging is disabled in render.yaml and start-local.ps1 because OAuth callbacks contain authorization codes/state. Do not enable request-body, response-body or URL query logging on OAuth endpoints. Provider HTTP logs are suppressed; failures log only a platform name. Hosting infrastructure may keep request logs separately; control their retention/access in the hosting account.


Meta timing compatibility: token exchange may omit expires_in. Both Meta callbacks inspect the issued user token with /debug_token, verify the app and user, and honor the earlier token/data-access deadline. Missing or invalid verification fails closed. When Meta explicitly reports zero for both deadlines, ClipBot uses a conservative one-day local verification window rather than assigning an assumed 60-day lifetime. This is not a guarantee against provider revocation; future worker access must revalidate authorization.
