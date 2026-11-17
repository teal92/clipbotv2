# Launch hardening progress — 2026-10-14

This is interim evidence, not the final production audit or launch approval. TikTok privacy restriction is specific to the owner's current developer account and is not a generic launch gate.

## Completed code and verified checks

- A 63-package hash-locked CPython 3.12/Windows x64 build environment was resolved from official PyPI wheel records without installing or upgrading the working environment. The locked resolver acceptance passed. A clean installation/build remains outstanding.
- Release packaging fails closed on missing corresponding-source/lock evidence, missing/changed inputs, unsafe paths, duplicate entries and environment inventory drift. Media tools now use explicit verified project paths, not mutable PATH.
- All four model hashes match the existing source model and staged model copy. Model verification precedes native model import/load. Unexpected loader configuration is rejected. Download cache metadata is not included in packaging.
- Bundle audit rejects customer media (including edited clips), job/recovery records, personal feedback, credentials, database files and encrypted backups; empty/missing/linked bundles cannot be certified. The existing unsigned bundle passed this content-only audit.
- New local-only adversarial tests reject report multipart uploads and extra attachment/recipient/HTML/command fields. Mail remains text/plain to a fixed recipient with no attachments. Executable-looking submitted text is not executed. Existing durable abuse/attempt limits remain.
- Davey accepts only a bounded candidate JSON shape and no action/tool/package fields. Injected transcript instructions remain user data; no provider tools are available. Provider responses containing tool blocks remain rejected. These checks use mocked providers and do not claim every model will ignore every injection.
- Customer installer access has a separate default-off CLIPBOT_COMPANION_PUBLIC_RELEASE switch. It requires authenticated verified email/current policies and a privately stored operator-attested production manifest, checked file hash, signing/provenance/clean-machine acceptance flags. Customer start still requires live paid coverage and owned ready companion. Legacy external installer URL settings no longer bypass this route or leak through workspace.
- Shared runtime/build version is 0.2.8. Server keeps its current installed-version requirement until an explicitly verified replacement installer is present. Internal owner QA is possible before public release.
- Portable recovery export uses a hidden interactive local passphrase, Argon2id and authenticated AES-GCM. No passphrase in command arguments/environment/chat; no plaintext master-key file. Tampering/wrong unlock/malformed envelopes fail. Synthetic export and restore tests passed. Owner chose a second computer; real export/transfer and that computer's restore proof remain pending.

## Current advisory check

At 2026-10-14T22:16:58Z, OSV returned no listed advisories for the exact 63 pinned PyPI packages, with no pagination outstanding. This is a published-advisory lookup, not binary malware detection, native-library certification or a guarantee. API: https://google.github.io/osv.dev/post-v1-querybatch/ . Full safe result is saved outside the repository in launch-dependency-advisories.json.

## Source/toolchain progress and unresolved gates

PyAV v18.0.0 commit 54a4395bb4cdd9cdd53ff6216c50b69f6475c13d vendor configuration selects pyav-ffmpeg 8.1.2-1 commit a71bf9279f7a4659154b68ba6783e89be460bcd5. Exact scripts and patches are now identified, replacing the prior comparison against current master:
- https://raw.githubusercontent.com/PyAV-Org/PyAV/v18.0.0/scripts/ffmpeg-latest.json
- https://github.com/PyAV-Org/pyav-ffmpeg/tree/a71bf9279f7a4659154b68ba6783e89be460bcd5
- https://raw.githubusercontent.com/PyAV-Org/pyav-ffmpeg/a71bf9279f7a4659154b68ba6783e89be460bcd5/scripts/pkg.py

Remaining: exact vendor archive correspondence, independently hash-verified source archives, MSYS2 runtime source/package inventory, historical fetched build helpers, per-DLL licensing/linkage analysis, and complete public corresponding-source package. Gyan's tag identifies the FFmpeg source commit but not a complete build/source recipe. Both distribution-source gates remain open.

The inspected ISCC.exe has a valid Windows Authenticode signature and publisher Pyrsys B.V., confirmed as the official publisher by https://jrsoftware.org/isdl-verify.php . Its file/product version resource is 0.0.0.0. Exact compiler release/component hashes still need complete verification before execution; no compiler was run in this audit.

Production artifact manifest must be private operator release evidence; clients cannot submit or modify these flags. Public distribution remains disabled. A build emits internal channel with cleanMachineAccepted=false and measures actual Authenticode status. This must not be relabeled production before real acceptance.

## Still needed

Complete source/license/toolchain verification, build and clean-machine install/update acceptance; trusted publisher signing route; real Stripe lifecycle acceptance with owner financial actions; encrypted recovery export/second-computer drill and authorized backup/monitoring operations; owner fresh-email customer journey; final deployed website/Davey/email/file-security audit. Public signup, live charging, customer AI and public installer release remain disabled until acceptance.

## Final regression evidence

After the last code review: 696 backend tests passed in 188.47 seconds; 185 frontend tests passed. Dependency consistency and whitespace checks passed. The release verifier was run and intentionally rejected packaging because corresponding-source evidence remains incomplete. No paid service, live charge, real AI call or social post was made in this work.

## Follow-up evidence after the initial audit

The portable recovery export was created and verified against the real encrypted backup on the owner computer. Recovery instructions and pinned tools are in the approved local backup folder. Transfer and restore on the second computer still require evidence.

The clean CPython 3.12.14 Windows x64 environment was installed from the hash lock. pip 26.2.1 is now included, bringing the exact approved inventory to 64 distributions; dependency consistency passed. The earlier 63-package OSV lookup does not include this added pip version.

All 15 vendor component/tool source archives now match their expected digests, and pinned PyAV/vendor source-tree file contents were checked against upstream Git blob entries. Executable code sections of all 25 wheel DLLs match the vendor output, with 11 full-byte matches; the other 14 are now fully explained by bounded static import-name repair reconstruction, without native execution. This does not independently reproduce the repair tool or fulfill source/license obligations. Several compiler DLL detached signatures passed vendor verification. Only compiler help and the validated signature checker were executed. Complete source, licensing, compiler and clean-machine release evidence remains unfinished; see NATIVE-SOURCE-REMAINING.md for current details.

A valid 1,000-character Unicode description could exceed the previous 4 KiB local request bound. The bounded feedback allowance is now 8 KiB, with a real local route regression that checks valid Unicode and rejects larger requests. Independent review found an ARM64 acceptance gap in the claimed x64 build check; it now checks the interpreter build platform and rejects ARM64. No customer files, real posts, paid AI calls or charges were used.

The follow-up OSV batch checked all 64 exact approved Python distributions and returned no listed vulnerabilities or pagination tokens. This is an advisory lookup, not a malware guarantee. The pre-deployment encrypted backup saved on 2026-10-14T23:40:55Z verified matching content for all 57 tables, database integrity and foreign keys; required recovery settings were present. No plaintext backup or secret was displayed.

Final follow-up regression: 701 backend tests passed in 191.62 seconds after the architecture review fix; 185 frontend tests passed. Exact 64-distribution/runtime verification, pip dependency consistency and whitespace checks passed. Source-completeness verification still intentionally rejects packaging. Independent code review found no remaining important issues in these changes.
