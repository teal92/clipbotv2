# ClipBot gateway attribution release design

Status: proposed; external changes require explicit approval. Public signup remains disabled.

## Exact external changes

Only clipbot.your-domain.example would be proxied. Existing DNS for other websites and email remains unchanged.
A hostname configuration rule would enforce Full (strict) TLS for ClipBot only.
A hostname request-header transform would overwrite X-ClipBot-Client-IP from ip.src, and overwrite X-ClipBot-Edge-Token with a new random secret shared only with the existing private ClipBot service.
The application would accept the single public IP header only after constant-time token validation and configured deployment checks. No native proxy IP allowlist or arbitrary forwarded header would establish trust.
This is authenticated gateway attribution, not an HMAC signature and never customer authentication.
The marker would not be returned by an API, logged or sent to browsers. Its encrypted recovery copy belongs in the approved backup.

## Acceptance checks

Before enabling attribution, test correct and incorrect tokens, duplicate headers, missing headers, private/reserved IPs, conflicting standard forwarded headers and direct-origin requests. Verify Cloudflare overwrites visitor-supplied custom headers and that TLS, authentication, OAuth callbacks and signed platform webhooks still function. Confirm no caching of authenticated API responses. Keep public signup off until real email delivery and edge acceptance pass.

## Rollback

Disable the new application trust profile first. Remove hostname rules and return only the ClipBot DNS record to DNS-only. Do not modify unrelated websites.

## Primary references

https://render.com/docs/configure-cloudflare-dns
https://developers.cloudflare.com/cloudflare-for-platforms/cloudflare-for-saas/saas-customers/provider-guides/render/
https://developers.cloudflare.com/ssl/origin-configuration/ssl-modes/
https://developers.cloudflare.com/rules/transform/request-header-modification/
