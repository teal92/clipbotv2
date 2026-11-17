# Companion release checks — October 15, 2026

Later update: the old native inputs below have been replaced by a locally built private 0.2.8 candidate. See [self-build results](COMPANION-SELF-BUILD-RESULTS-2026-10-15.md). This earlier report remains the historical audit of the superseded binaries; public release and clean-PC acceptance are still pending.

**Result: release blocked.** No new customer installer was built or published. No protection was bypassed and no paid service was added. The other launch work remains parked.

## Completed

- All 195 pinned release inputs match their recorded sizes and SHA256 hashes. The Python 3.12.14 Windows x64 runtime and exact 64-package build inventory match policy.
- A fresh advisory scan checked all 64 pinned runtime/build packages, with no listed vulnerabilities or skipped packages. Microsoft Defender's report-only custom scan of the staged native/build tools reported no threats; that is not a malware guarantee or a scan of a not-yet-built installer.
- Package notices were incomplete and unpinned. Added 140 notice files covering the 64 reviewed distributions, Python and Inno Setup license texts, exact Gyan README, and machine-readable notice inventory. The three wheel-omitted package licenses were fetched from official immutable upstream version commits. All compiler and license files are now covered by the release manifest.
- Fixed the installer upgrade case where unchecking startup could leave the old startup registration enabled. The recipe now removes only ClipBot's per-user startup value before applying the selected task. The regression check failed before the change and passes afterward.
- The authenticated, hash-pinned Inno compiler successfully compiled a synthetic recipe fixture. The output is clearly named RECIPE-CHECK-DO-NOT-INSTALL.exe, contains no companion, was never executed and is not a release candidate.
- Reverified 17 previously acquired source archives. Completed the five-patch inventory from the verified immutable PyAV build-source tree. This does not close native corresponding-source gaps.
- A real local source-mode smoke check loaded the pinned Whisper model, recognized offline synthetic speech and rendered a 15-second 1080×1920 H.264/AAC video with subtitles. No paid Claude calls, network capture, social posts or customer recordings were involved. This does not establish frozen/installed acceptance.

## Still required

1. **Matching native source/build records.** Gyan's exact full-build source recipe remains unavailable in the inspected public evidence. PyAV's historical copied Windows GCC/iconv/winpthread/zlib runtime source/package identities are unresolved. The authenticated GitHub connector returned HTTP 410 for both identified vendor job logs. Obtain the exact records or replace those binaries with a reviewed reproducible build. The manifest deliberately retains sourceComplete=false.
2. **Publisher signing.** No usable code-signing certificate was found in this PC's Windows certificate stores. An external credential/service may exist; the owner question remains open. A self-signed certificate is not a trusted-publisher substitute. No purchase/enrollment is authorized by this report.
3. **Physical acceptance.** The owner selected a second Windows PC. A fresh install, upgrade, startup opt-out, uninstall/reinstall, and final artifact antivirus/signature check on that PC have not been performed. Use COMPANION-SECOND-PC-ACCEPTANCE.md after a verified candidate exists.

The release verifier is expected to continue blocking the real build. Passing source-mode tests and compilation of a dummy fixture cannot turn these remaining checks into passes.

## Primary references

- FFmpeg redistribution guidance: https://ffmpeg.org/legal.html
- Gyan build documentation: https://www.gyan.dev/ffmpeg/builds/
- Pinned PyAV build source: https://github.com/PyAV-Org/pyav-ffmpeg/tree/a71bf9279f7a4659154b68ba6783e89be460bcd5
- Inno registry flags: https://jrsoftware.org/ishelp/topic_registrysection.htm
- Microsoft Defender custom scan/report-only options: https://learn.microsoft.com/en-us/defender-endpoint/command-line-arguments-microsoft-defender-antivirus

## Final verification

69 companion-focused security/regression tests passed in 15.02 seconds. The 195-file hash check and complete notice/package inventory check passed. The real build gate remains closed because corresponding-source evidence is incomplete. No release installer was executed or installed on either PC.

Installed-distribution integrity check: all 11,332 hashed files across the 64 packages matched their local wheel RECORD digests; 9,295 unhashed metadata/cache records were not certified by that check. No checked record escaped the build environment. Local RECORD checks supplement the independent wheel hashes in the reviewed lock; they do not replace upstream provenance.

Byte-preservation rules were added for hash-pinned notices and lock/inventory files so Git line-ending conversion cannot silently invalidate a later build. Original third-party license whitespace is preserved. Installer publisher metadata now uses YOUR COMPANY NAME; this metadata is not a digital signature.

All 155 tracked hash-pinned release inputs also matched their staged Git bytes after byte-preservation rules were applied. The other 40 pinned inputs are verified local tool/model artifacts excluded from Git.
