# Companion native replacement build

Authorized scope: replace the incomplete third-party native build records with locally built, recorded inputs; preserve the existing capture, transcription, rendering and pairing interfaces. No production change or public release is authorized by a successful compilation alone.

## Design and execution

1. Use official Microsoft-signed vcpkg client release 2026-09-26 and MSVC toolset directory 14.44.35207. Pin Microsoft's registry to `c52f7bd748185ef0e0daf033d9f2ddfc8a3449ea`; retain fetched source archives, port patches, compiler identity, build logs, package ABI metadata and output hashes.
2. Build FFmpeg 8.1.2 for the PyAV 18.0.0 source already acquired from its immutable upstream commit. The decoder profile uses shared FFmpeg libraries without GPL/nonfree features. Build PyAV against those libraries instead of shipping its old vendored MinGW DLLs.
3. Build separate static command-line FFmpeg/ffprobe tools with x264 and libass for the current H.264 rendering and subtitle pipeline. Keep GPL renderer tools in separate processes; never link their GPL-enabled libraries into the decoder profile. Do not enable nonfree features. Audit the actual resulting configuration and runtime imports rather than assuming the manifest proves the boundary.
4. Use isolated `C:/Users/<you>/cb-build` work/cache/output paths and disable shared binary caches. No server keys, customer databases, personal clips or existing companion pairing state enter the build.
5. Archive matching source, patches, notices and build instructions; independently inventory all resulting DLLs and executables. Only update the release lock, notices and manifest after successful build and review. Keep `sourceComplete=false` until correspondence is actually established.
6. Test real local transcription, audio extraction, stream-compatible demuxing, captioned vertical H.264/AAC output, frozen imports and setup readiness. Compare behavior with the existing source-mode smoke check. Scan final outputs and perform clean second-PC install/update/startup/uninstall tests before promotion.

## Risks and acceptance

Compiler/ABI and FFmpeg changes can break PyAV imports or media decoding. Missing font, TLS, subtitle or codec features can break capture and rendering. Two native profiles must stay isolated in packaging. Regression checks cover these boundaries; failed builds or scans do not relax the existing release gate.

Publisher signing is separate and remains undecided. No paid tooling, consulting, certificate purchase or public download is part of this build step. Retain the currently working companion unchanged.

Status: replacements and a private unsigned installer have been built and locally tested. See [actual results](COMPANION-SELF-BUILD-RESULTS-2026-10-15.md). This plan alone is not acceptance evidence; clean-PC installation and public release remain pending.
