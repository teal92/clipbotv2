# Companion 0.2.8 self-build results

**Result: private unsigned installer built; public release not accepted.** The newly built components replace the Gyan executables and PyAV vendored MinGW binaries whose historical corresponding-source records were unresolved. We do not need those historical records to establish the provenance of these replacement outputs.

Update: the installer was subsequently hosted behind the existing owner-only download, checksum verified, and the owner confirmed successful fresh installation and pairing on the second PC. The private website now requires 0.2.8. The build-time account below is historical; the current technical audit and remaining public-release gates are in [the final audit](FINAL-SECURITY-AUDIT-2026-10-15.md). The user downloads directly from ClipBot; a transfer folder is unnecessary.

## Actual artifact

- Installer: `packaging/dist/ClipBotCompanionSetup.exe`
- Version: `0.2.8`; 368,165,966 bytes (351.1 MiB)
- SHA256: `45439f39087d193d82f3efca9a52cdf3769dfa4dfc83a0d0b8dbc740b76344f0`
- Authenticode: **NotSigned**; manifest channel **internal**, `provenanceVerified=true`, `cleanMachineAccepted=false`, `signed=false`.
- Checksum-verified handoff: `C:/Users/<you>/Documents/ClipBot Companion 0.2.8 - PRIVATE TEST`. Read its private-test instructions before transferring it to the second PC.

No installer was installed on either computer during this build. The existing working companion, startup registrations, pairing and live hosted service were not changed. Public signup, customer AI and installer release were not enabled.

## Build correspondence

Used official Microsoft-signed vcpkg release 2026-09-26 (SHA256 `2a4ae1467b9e797964c60c919d057b9e5dc1ec03f4b9632c1150026db25201f2`), registry commit `c52f7bd748185ef0e0daf033d9f2ddfc8a3449ea`, and installed MSVC toolset directory 14.44.35207 (compiler reports 19.44.35229).

- Decoder: seven locally compiled FFmpeg 8.1.2 shared DLLs, LGPL configuration, GPL/nonfree disabled. Actual export/configuration and x64 import checks passed; the five undocumented legacy MinGW/runtime DLLs are absent.
- PyAV 18.0.0: compiled from upstream commit `54a4395bb4cdd9cdd53ff6216c50b69f6475c13d` against those decoder DLLs. The repaired wheel SHA256 is `767e92d2fcdb6b982706616670b7eeb20f7a388afacc55821886435465164a6f`.
- Renderer: separate static FFmpeg/ffprobe 8.1.2 processes, x264, libass and Windows SChannel TLS. The actual executable import lists contain Windows system libraries, not the old MinGW runtime. GPL renderer libraries are not linked into PyAV.
- Microsoft runtime: four explicit unmodified signed runtime inputs from Visual Studio's x64 redistributable folder, version 14.44.35211.0. An initial packaging attempt selected a runtime from an unrelated PATH directory; that preliminary wheel was retained separately and is **not** used in this candidate. The controlled wheel and frozen runtime hashes were verified.
- Corresponding sources: 11 installed native-package source records matched their cached archive digests. The source bundle contains 107 hash-inventoried files with component sources, patches, recipe snapshots, build configuration and notices. The bundle is shipped inside the installer at `_internal/licenses/native/corresponding-source.zip`.
- Source archive SHA256: `ae28e60378263af8012179d92c156e99e38d7f4b43aa3d81de0949743fe72e09`; size 98,434,538 bytes. Proprietary Microsoft tools are not represented as open source. Bit-for-bit reproducibility has not been established.

The release manifest now pins 214 inputs. A new build check compares installed PyAV code and native bytes against the exact pinned local wheel, rejects substitutions despite equal version numbers, and rejects extra native files, duplicates and unsafe paths. The original environment with the vendor wheel intentionally cannot pass that check. Use the separate verified `C:/Users/<you>/cb-build/worker-env` for this candidate; the existing environment was preserved.

## Tests and security checks

- Final affected companion suite: **44 passed** in 5.05 seconds. Initial red tests established the missing wheel-correspondence check before its implementation.
- Public-release/download gate suite: **15 passed** in 6.28 seconds; an internal unsigned candidate does not satisfy the customer production-release conditions.
- Exact 64-package runtime/build inventory and Python 3.12.14 Windows x64 verified; dependency consistency passed.
- Fresh advisory scan: no listed vulnerabilities in the exact 64-package release environment. The newly created tool environment initially inherited vulnerable pip 25.0.1; it was replaced with pinned pip 26.2.1 and the seven-tool advisory scan passed. These scans do not cover all possible native-code defects.
- Actual source-mode acceptance: synthetic H.264/AAC decoding, pinned local Whisper transcription and captioned 15-second 1080×1920 output passed. Captions were visually inspected.
- Actual frozen application: all 56 PyAV binary files matched the built wheel, all four Microsoft runtimes matched pinned inputs, and the embedded source archive matched. Frozen diagnostics passed tool/model readiness, model load, transcription, rolling capture/extraction, review preview and vertical rendering.
- Frozen diagnostics ran with isolated per-process AppData and a restricted tool search path. No real pairing, live capture, paid AI requests or social posts were performed.
- Bundle private-data audit passed. Microsoft Defender's signed scanner ran in report-only mode over the final installer and frozen distribution: exit 0, **no threats found**. Signatures: 1.461.37.0, last updated October 15 at 1:22 AM Eastern; antivirus/real-time protection enabled. This is a scan result, not a guarantee of harmlessness.
- Independent review found no important security/correctness findings. Its rebuild-documentation suggestion was incorporated before final source bundling and compilation.

Build, download, source, repair and scanner logs remain in the isolated `C:/Users/<you>/cb-build` directory. No paid consulting or signing service was used. Current Claude caps and billing were unchanged.

## Still pending

Perform standard-user clean installation, startup/duplicate checks, older-version upgrade, uninstall/reinstall and a final installed-device journey on the second PC. The hosted required version has not been switched, so the private handoff currently covers installation/setup rather than full live monitoring. Keep the signed-publisher/public-download gate closed until its separate decision and acceptance are resolved. The final deployed website security audit is a separate launch step.

Primary references: [FFmpeg redistribution guidance](https://ffmpeg.org/legal.html), [FFmpeg security releases](https://ffmpeg.org/security.html), [Microsoft runtime redistribution](https://learn.microsoft.com/en-us/cpp/windows/redistributing-visual-cpp-files), [Microsoft distributable-code list](https://learn.microsoft.com/en-us/visualstudio/releases/2022/redistribution).
