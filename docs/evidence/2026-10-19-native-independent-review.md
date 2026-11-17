# Independent native companion review — 2026-10-19

Review range: ee92661f7ab3ff344a2702dceef80c27c1f0657c through f37d8fe. One user-authorized independent read-only reviewer; no implementer agents or duplicate reviewers.

No actionable P0/P1/P2 findings. Apple Silicon is suitable for the explicitly approved experimental public beta, conditional on final regression results and exact-asset publication checks. This is not real desktop acceptance.

The reviewer independently hashed the local 480,827,382-byte DMG: f32eed0e59b28666003ff98b6f2956828fbfab67dcfec1ef428e7b75eaed43e8, matching the source-0a74d3b receipt. Later website/build changes do not change this packaged ARM worker.

Reviewed: account/policy/CSRF and per-artifact acknowledgement; target/version isolation; native credential storage; handoff/startup/shutdown; TLS enforcement; dependency/source/archive verification; package audits; frontend platform selection; workflow permissions; and fixed-asset remote delivery.

Considered and set aside with explicit reasons:

- Public binary accessibility: authorized; normal pairing, worker lease and paid coverage remain necessary to operate.
- Missing desktop acceptance: disclosed; manual acceptance flags stay false under the approved experimental beta.
- No verified Apple Developer ID/notarization: disclosed before per-artifact acknowledgement.
- Remote transfer integrity: fixed repository/asset ID, filename/version, digest/size and HTTPS redirect host checks.
- Windows regression risk: existing release bytes and legacy DPAPI/report paths remain separate.
- Whitespace diagnostics: upstream patch whitespace/trailing blank line, no functional issue.

Intel remains unavailable: current ONNX source wheel, receipt and source-closure integration plus complete package checks are required even if its separate source compilation passes. Linux remains unavailable until its own complete package check passes. Real desktop/keyring/tray/install/pair/startup/update/uninstall acceptance on the stated platforms remains unverified. Review performed no native desktop actions, deployments or paid API calls.
