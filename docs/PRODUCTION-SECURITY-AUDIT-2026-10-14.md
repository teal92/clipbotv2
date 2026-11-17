# ClipBot production security audit — October 14, 2026

Operator: YOUR COMPANY NAME, YOUR STATE. Scope: release based on c4168ac, customer access, billing limits, local worker boundaries and the replacement Render service. This is a practical security assessment, not a compliance certification or a claim that public paid launch is approved.

## Verified changes

- Customer email verification uses 256-bit, purpose-bound, hashed, 15-minute, single-use tokens tied to the signed-in account and its stored email. Tokens arrive in a URL fragment, are removed immediately, and are never saved in browser storage. Password-reset tokens cannot verify email and verification tokens cannot reset passwords.
- Current-version Terms, Acceptable Use and Privacy acceptance is recorded with its first acceptance time. Paid checkout, plan changes, new AI reservations, capture admission and upload admission check email ownership and current policy acceptance when enforcement is enabled. Finishing already-authorized operations remains possible.
- Public signup forces these gates and fails closed without configured email delivery and verified ingress. The explicitly configured owner retains private diagnostic access only; this does not bypass plan or spending limits.
- Recovery quotas now charge account, address and global scopes atomically. Rejected requests cannot consume the shared allowance. Delivery stays generic, authenticated destinations are stored account emails, and requests cannot supply attachments or alternative recipients.
- Replacement checkout requires provider confirmation that the previous subscription is terminal. A past-due or recovering subscription cannot create overlapping recurring billing. Provider identity, customer, metadata and concurrent state are checked.
- Canceled or failed worker jobs revoke their local preview capabilities without deleting source files. This source change needs a newly built companion before installed users receive it.
- Application protection bounds read, chat, authentication, provider, write, concurrent and streaming work. Expensive/write quotas persist; read/chat quotas stay in memory. Identity is verified from sessions/devices. Authentication work has an aggregate bound against distributed password attempts. Limits are for one server worker, not distributed infrastructure.
- Client headers affect quotas only after an explicit deployment trust profile, private socket peer allowlist and valid single public CF-Connecting-IP. Forwarded headers never provide authentication or a local-development bypass. Default attribution uses the socket peer. Private operator ingress diagnostics return safety flags without client identities or credentials.

## Evidence

- Full isolated release suite: 543 backend and 157 frontend tests passed. Additional private ingress-diagnostic regression is recorded in the final release checks.
- Official package vulnerability audit checked 39 hash-locked server packages and 64 installed worker/build packages. After updating build-environment pip to 26.2.1, both inventories had zero known vulnerabilities and zero skipped packages. This does not certify bundled binaries or dependency provenance.
- A limited credential-pattern scan of 135 release source files found no matches; Git history and unrelated local files were outside this scan.
- A private SQLite backup/restore drill matched all 51 source tables, passed integrity and foreign-key checks, and downloaded no customer records. Offsite disaster recovery and encryption-key restoration still need operational acceptance.
- Public live checks verified HTTPS, HSTS, CSP, no-store, framing denial, private account/operator routes, closed docs/config/database paths, and cross-origin checkout rejection.
- Persistent disk free space increased from 179 MiB to 564 MiB after removing only the unused prior installer. Its exact size and checksum matched the retained local 0.2.6 archive; active 0.2.7-beta and customer data were preserved.
- Render documents automatic Cloudflare DDoS protection; live responses carry Cloudflare and Render origin headers. Those headers alone do not prove safe client attribution. A live forged-header ingress test must pass before trusting the optional proxy profile. Application controls are a backstop, not a custom edge WAF.

## Remaining launch gates

1. Configure authenticated outgoing email privately and prove real verification, recovery, delivery failure/bounce handling and support delivery. No SMTP connection exists yet; public registration must stay closed.
2. Verify the deployed ingress overrides forged client headers and safely allowlist the actual proxy peers before enabling the trust profile. Preserve fail-closed signup if topology changes. Verify operational alerts and provider account security/MFA.
3. Finish explicit live billing, cancellation/management, renewal/refund/tax requirements and two-customer provider acceptance. Current code remains sandbox-only. Existing $400 monthly/$20 daily global AI caps are unchanged.
4. Rebuild, sign and verify the companion on a clean machine. The currently served 0.2.7-beta installer is unsigned and does not contain this preview-revocation fix. Pin build/binary provenance and document local media retention/deletion.
5. Complete real multiuser capture-to-publish acceptance and provider approval. TikTok developer-account posts remain private until provider approval; reconcile unknown outcomes before any retry.
6. Test expected 10–30-user load, SQLite contention, disk growth, offsite backup/restore including keys, rollback, service recovery and monitoring. Fixture capacity tests are not a hosting load benchmark.
7. Complete business/legal review, maintained retention/deletion/export procedures and applicable disclosures. Production policy wording does not substitute for legal review.

## References

- [Render DDoS protection](https://render.com/docs/ddos-protection)
- [Render inbound request handling](https://render.com/articles/how-render-handles-ddos-attacks)
- [Cloudflare request headers and trust caveats](https://developers.cloudflare.com/fundamentals/reference/http-headers/)
- [OWASP ASVS](https://owasp.org/projects/asvs)

## Live release acceptance

Security release 69793ab was manually deployed to the existing replacement service. Normal private ingress diagnostics confirmed Render, a private socket proxy peer, Cloudflare ray and a public CF-Connecting-IP. Two forged CF-Connecting-IP/X-Forwarded-For probes (documentation address and public address) were rejected at Cloudflare with HTTP 403/error 1000 before reaching the application. No customer data or credentials were returned. The optional header-trust profile remains disabled: a single observed proxy address is not proof of a stable trusted network range. Application quotas remain active, and public signup remains closed pending SMTP and stable quota attribution.

Final protected ingress regression: 8 focused tests passed in addition to the 543 backend/157 frontend full run. Independent security review found no high or medium blockers for the current private deployment. These results do not approve public paid launch.
