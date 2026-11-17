# Final technical security audit — October 15, 2026

Public launch remains closed. This report supersedes older checkpoint descriptions of billing, native-build provenance and installer availability. It records tested technical boundaries; it is not a guarantee that every possible defect has been found.

## Release and owner acceptance

The owner confirmed downloading companion 0.2.8 from the authenticated website, installing it and pairing it successfully on a second Windows PC. The hosted installer matches SHA256 `45439f39087d193d82f3efca9a52cdf3769dfa4dfc83a0d0b8dbc740b76344f0`, 368,165,966 bytes. The prior installer is retained privately for rollback.

The hosted manifest remains internal and unsigned. The owner chose preparing an explicitly disclosed unsigned beta. The install/pairing confirmation does not establish the entire upgrade/uninstall matrix or publisher signing. No flags were falsified to pass the signed-production gate. Second-PC recovery testing remains deferred by the owner.

## Audit findings and corrections

Independent review found that canceled/expired customers could still submit review decisions, advance learning history or register edits/artifacts using an old valid device lease. Paid AI and publication were already blocked. The final patch checks the common entitlement boundary within each mutation's immediate SQLite transaction: review decisions, edit begin/complete, candidate-preview registration and rendered-artifact registration. Confirmed cancellation, cancellation awaiting provider reconciliation and subscription expiration are covered by new regressions. Cleanup remains available.

New private maintenance controls were independently reviewed. Follow-up corrections prevent new pairing/redemption while the visitor site is closed, preserve sidebar navigation after a refresh, and avoid claiming that an uncertain request made no changes. No unresolved important finding remains from the inspected paths.

## Evidence

- Complete ClipBot regression suite: 866 passed in 266.61 seconds. Final focused maintenance/operator/edge/cancellation checks: 26 passed in 7.87 seconds after the pairing-exemption correction. Frontend suite: 199 passed.
- C2 backend suite: 75 passed in 20.555 seconds. All 12 frontend check files passed. Tests use synthetic accounts, databases, private adapters and no real charges, paid AI or social posts.
- Refreshed advisory scans: 39 exact server packages and 64 exact companion packages; zero listed vulnerabilities and zero skipped packages. Installed dependency consistency passed. This does not audit every native codec defect.
- Limited credential-pattern scan: 525 tracked source/document files at the start of this pass, zero matching embedded credentials. Findings never include raw credential values.
- Live pre-deployment probes on `6194620`: HTTPS health 200; account/operator/download endpoints reject unauthenticated requests with 401; schema/docs, environment and database paths return 404; cross-origin checkout returns 403; unsigned billing webhook returns 400. A request with spoofed edge-token/client-IP headers was blocked with 403.
- Live database: integrity and foreign-key checks passed across 68 application tables. Persistent disk had 211 MiB free after retaining current and rollback installers. Media processing remains local to customers' devices.
- Email configuration is enabled, uses the notification subdomain, fixed official report recipient and mandatory verified TLS. Earlier verification/reset/report Inbox receipt is owner-confirmed; no new mail batch was sent during this audit.
- Free-mail launch capacity remains bounded: at most 50 verification send requests in a rolling day (including resends) and 90 combined email attempts/day, 2,700/month. Those safety limits mean a 250-customer same-day signup surge is not supported by the current mail configuration. No paid email service or automatic overage was enabled. A capped initial beta fits these limits; higher signup volume requires a separate reviewed capacity decision.
- The unchanged final installer/frozen bundle previously passed report-only Microsoft Defender scanning with no threats found. Pinned local media decoding, transcription, rolling capture, caption rendering, native-wheel correspondence and embedded-source checks are recorded in the companion build report.

## Reviewed security criteria

Account/session authorization, CSRF/origin enforcement, password rules, verified email/current policies, invitation restrictions, worker/device ownership and revocation, capability-scoped local previews, bounded body/file handling, callback authentication, billing mode separation and event idempotency, atomic plan/budget limits, cancellation races, publishing consent/destination guards, malicious transcript/feedback handling, email abuse limits, fixed recipients and attachment rejection were inspected and exercised by the regression suites.

Davey has no package-install, shell or general-purpose execution tools. Transcript/context/feedback are untrusted structured data; output is schema/range/type bounded, personal preference memory is bounded and account/device scoped, and autonomy requires measured validation plus explicit server-owned consent. Prompt injection can still affect a model's judgment; it does not grant authority to change billing, execute code or publish without the independent server checks.

Support reports accept bounded plain text only. Client-selected recipients, attachments, multipart uploads, HTML bodies, executable fields and header injection are not supported. Account/IP/global limits and a durable outbox constrain mail abuse. No system can promise that every submitted sentence or link is benign, but it is not executed or delivered as an attachment by this path.

## C2 website switch behavior

Only the existing authenticated private operator connection can read/change persistent availability. C2 requires an owner session, same-origin request, fresh owner password and enabled authenticator/recovery verification, explicit confirmation, strict fields and the last confirmed revision. Commands are not retried automatically; connection failures show unknown/unconfirmed rather than success.

Closing returns a maintenance page/503 for visitor pages and APIs, including new companion pairings. Health probes, signed provider callbacks, private operator recovery and already-paired worker operations remain available. Existing companion sessions continue within plan/budget limits; this is visitor maintenance, not an emergency stop of the entire processing system.

Reopening restores the existing audience. It does not change the public signup, invitation, customer-analysis, billing or companion-release settings. The private-preview/public-registration distinction is displayed in C2. Schedules and announcements remain inactive. Other websites are not connected or changed by this ClipBot-only adapter.

## Deployment acceptance

The audited patch must be deployed and the actual C2 private connection verified before the controls are described as operational. Public launch activation remains a separate owner action after the remaining release decision and acceptance checks.

## Explicit unsigned beta policy

The prepared beta path does not redefine `production_ready` or label the installer signed. It requires both the public companion release switch and a separate unsigned-beta switch; a checksum-verified `channel=beta` manifest; verified provenance; the explicit `cleanInstallPairedAccepted=true` attestation corresponding to the owner's observed install/pairing; and a verified account with current policies.

Before a customer can download, the setup dialog prominently explains that Windows cannot verify YOUR COMPANY NAME as publisher and may warn. The customer must explicitly enable the unsigned-beta download. The CSRF-protected acknowledgment is stored for that account, version and SHA256. Direct downloads before acknowledgment fail; another account or changed binary must acknowledge separately. The full `cleanMachineAccepted` and `signed` flags remain false. Beta still has operational risks, including pending upgrade/uninstall acceptance; no antivirus weakening is requested.

Additional beta/download/companion checks passed (32 tests), all 200 frontend tests passed, and independent review found no critical/important bypass in the new beta path. The final complete suite, including beta acknowledgment, changed-artifact and version-adoption regressions, passed **876 tests in 311.12 seconds**. No new executable was built or changed by this website-only acknowledgment UI.

Automatic approval review rejected a direct push to main because that would publish live behavior without a specific release approval. Changes are being prepared on development branches and draft pull requests. No alternate path was used to change main or deploy around that rejection. The owner must approve the exact reviewed release before merge/deployment and final live acceptance.
