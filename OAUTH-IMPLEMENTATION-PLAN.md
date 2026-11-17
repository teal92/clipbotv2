# Account authorization implementation plan

Goal: Existing personal, creator and test accounts authorize ClipBot through official platform sign-in, without customer developer credentials.

Architecture: Shared persistent single-use ten-minute OAuth state, session binding and a separate HttpOnly SameSite=Lax callback cookie. Tokens encrypted with Fernet using CLIPBOT_TOKEN_ENCRYPTION_KEY; per-user/platform records. Fixed official provider endpoints; no user-controlled callback URLs or outbound URLs. Ordinary account sessions remain SameSite=Strict. Missing platform credentials disable only that platform.

1. Add encrypted OAuth storage and prove single use, expiry, session/cookie binding, isolation and encryption with tests.
2. Add Twitch/Kick/TikTok/Meta authorization, exchange and identity verification with mocked official endpoints. Kick uses PKCE. Meta discovers eligible Pages/linked professional Instagram accounts and requires destination selection. Never grant publishing eligibility based on the chosen guide type.
3. Integrate authenticated/CSRF-protected start, callback, destination and disconnect endpoints. Show real identity, connection state and honest publishing readiness. No media uploads or paid AI calls.
4. Add safe token refresh support and platform disconnection, avoid code/token logging. Tests cover revoked/expired tokens, provider errors, wrong state, wrong users and malformed replies.
5. Run existing checks, request independent security review, publish and give the owner exact Render environment and callback setup instructions. Preserve v1 callbacks.

Owner setup is required before live authorization: encryption key plus existing public app IDs/client secrets in Render, and exact new HTTPS callback URLs in existing developer apps. No secret values in chat or committed files. Actual platform app approval and live account testing cannot be simulated by unit tests. Local worker uploads remain a separate implementation gate.
