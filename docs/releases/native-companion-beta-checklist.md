# Native companion beta release checklist

## Release authorization

The owner approved the design, inline implementation and one independent whole-branch review. On October 19 the owner explicitly rejected a tester-email allowlist and authorized public beta distribution after review. This supersedes Task 9's original designated-tester restriction. No real desktop acceptance is inferred from this approval.

## Apple Silicon — 0.3.0-beta.1

- Native packaged automated acceptance: passed, GitHub run 39313855193, source 0a74d3b51a0ff3da381978d5d27aad54a9b3a7f5.
- Installer: ClipBotCompanion-arm64.dmg, 480827382 bytes.
- SHA-256: f32eed0e59b28666003ff98b6f2956828fbfab67dcfec1ef428e7b75eaed43e8.
- Minimum macOS: 14.0, Apple Silicon only.
- Independent review: no actionable P0/P1/P2 finding for this experimental release; see the evidence report.
- No verified Apple Developer ID or Apple notarization. Disclosure and exact-artifact acknowledgement required.
- Real desktop install, pairing, URL handoff, tray controls, startup preference, update and uninstall: unverified; customer will work with the owner as beta tester. Both manual acceptance flags remain false.
- Delivery: fixed asset ID in existing public ClipBotV2-setup-guide releases; no new paid service, server token or disk deletion. Original Windows release and rollback remain intact.
- Before publication: full regression checks, approved exact-asset metadata and anonymous download gate checks.
- After publication: verify the public asset ID/digest/size/redirect, deployed source and per-target status, protected account/consent behavior and Windows version/hash continuity.

## Intel Mac and Ubuntu/Mint

Remain unavailable until their individual source/dependency integration and full packaged checks pass. Do not substitute the Apple Silicon artifact, disable VAD, silently downgrade dependencies or claim desktop compatibility from a headless check.

## Rollback

Disable the native remote manifest by atomically moving it to a retained non-active filename, then restart the existing website service to rebuild the release catalog. This removes that target's download while preserving Windows. Never delete customer databases, modify paid coverage or disable TLS/account checks as a rollback step. Retain the tested binary, checksum and manifest privately for investigation.
