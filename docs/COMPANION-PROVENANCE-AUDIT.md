# Companion provenance audit — 2026-10-14

Read-only audit of release artifacts and public upstream metadata. No installer, media executable, model, or compiler was executed. No customer files, device credentials, logs, private download links, private keys, or personal certificate identities were read. No build, signing, installation, publication, or paid service was performed.

## Release identity and signature

Desktop/clipbot-saas/packaging/dist/ClipBotCompanionSetup.exe: 403710410 bytes; SHA256 `8ac810578b52c82dfad66aa5a8816d9ef688aa30cdd66e764aa6eb2f1fff874d`; Authenticode **NotSigned**. Dist companion EXE SHA256 `270e349f9e305c9694b34c006455ba20450ad0a17c708e31295ee801255995eb`, also NotSigned.

No certificate with code-signing EKU 1.3.6.1.5.5.7.3.3 was found in Windows CurrentUser/My or LocalMachine/My. This does not exclude a hardware token, remote signing account, or certificate held elsewhere. No identities or private keys were enumerated. Publicly trusted publisher signing is not currently available from the inspected stores; do not buy or enroll in a service without user approval. A self-signed certificate does not satisfy the trusted publisher release gate.

The separately inspected Desktop/cbot_v2_local_storage manifest is **0.2.6-beta**, SHA256 `e9fb2507b8ce3e81c1b0e35088d1a77f6b1cbdb93bd3ea3b5692b94b9d2f0f22`. Its main EXE differs from 0.2.7, although its media binaries match. No running ClipBot-named process was returned by Get-Process. The expected LocalAppData/Programs/ClipBotCompanion installation directory was absent. Therefore this audit verifies **dist 0.2.7**, not an installed 0.2.7 or clean-machine acceptance.

## Standalone FFmpeg/ffprobe

PATH resolves through WinGet Links to Gyan.FFmpeg package `ffmpeg-9.0.1-full_build`. Current PATH targets, dist 0.2.7 binaries and cbot_v2_local_storage binaries have identical hashes:

| File | Size in dist | SHA256 |
| --- | ---: | --- |
| ffmpeg.exe | 222229504 | 57c56e369d5b4873b4d93fc1a1d833cb7cd8bc9325c14b05c34ce60b22842d8a |
| ffprobe.exe | 222026240 | afe05347caaabe479b3c4eae71992b6ec1e11c57266a1d665deb0f9fe9847208 |

Both are unsigned. Installed Gyan README identifies GPLv3, upstream FFmpeg source commit `bf1b838f2a`, build version 9.0.1-full_build-www.gyan.dev. Existing FFmpeg-build.txt records GCC 16.1.0 and `--enable-gpl --enable-version3 --enable-static` with numerous external libraries. README lists precise versions/commits for external libraries; that README is not bundled by the spec.

Public [Gyan release 9.0.1](https://github.com/GyanD/codexffmpeg/releases/tag/9.0.1) confirms FFmpeg commit bf1b838f2a. Public release API provides full-build.zip archive digest `2e8e28af97c2ae338ccef92e36da9b2a4cd21d0cad9dde093545606cb07f5b00` (251427729 bytes); full-build.7z digest `4b9c814cb07a1f90d05b768ef4eb2abbf89af94bbb924df5b7dbd6e64e1e2b96` (165742351 bytes). The official ZIP was subsequently fetched into memory and verified against that digest; both executable entries were hashed without executing or installing them. Their bytes exactly match dist and current PATH targets. Binary origin is verified; complete corresponding source remains outstanding.

Current notices provide generic repository links, not complete matching source with included external libraries, patches and build scripts. No complete corresponding source archive or source availability artifact was located in packaging. Source availability is a release blocker. [FFmpeg primary licensing guidance](https://ffmpeg.org/legal.html) requires exact source correspondence and covers external linked libraries; [Gyan build documentation](https://www.gyan.dev/ffmpeg/builds/) identifies all variants as GPLv3.

## Additional FFmpeg copies via PyAV — significant gap

Dist also bundles `av.libs` from PyAV 18.0.0: avcodec-62, avformat-62, avutil-60, avfilter-11, avdevice-62, swscale/swresample, libx264-165, libx265, and other libraries. Static inspection of avcodec DLL SHA256 `777704d8914bb99e5d78f3a0e7424031b5376621f2e7c60e83b84e77fcc7e2d7` confirms embedded FFmpeg version **8.1.2** and license string **LGPL version 3 or later**. Its configuration enables version3, shared libraries, libx264 and libx265, without enable-gpl. Thus the mere presence of x264/x265 does not prove the avcodec DLL declares itself GPL. The current [official FFmpeg patch](https://github.com/PyAV-Org/pyav-ffmpeg/blob/master/patches/ffmpeg.patch) removes libx264/libx265 from FFmpeg's external GPL list; current master is not yet tied to the old wheel's exact build revision. This warrants review of actual linkage, matching patches and each DLL's licensing; it does **not** establish that changing the configure list changes third-party license obligations, or justify a definitive combined-work conclusion.

These DLLs are separate from Gyan FFmpeg 9.0.1 and require separate exact source/build provenance. Removing standalone FFmpeg does not solve this gap. PyAV's Python wrapper BSD license is not a substitute for linked-library licenses. The dist av directory has no copied LICENSE/AUTHORS, and av dist-info is absent even though the venv contains av-18.0.0.dist-info/licenses/LICENSE.txt. [Official PyAV binary-build repository](https://github.com/PyAV-Org/pyav-ffmpeg) documents the separate build source; the matching wheel build revision remains unverified. Public PyPI identifies the compatible Windows wheel `av-18.0.0-cp311-abi3-win_amd64.whl`, SHA256 `aaf4d354d2beaa6651e4f92e54409a578bde64f79c0beef9a30b388d06f7c629`, 27556236 bytes; the wheel was subsequently fetched into memory and hash-verified. All 25 bundled av.libs DLLs match the corresponding upstream wheel entries byte-for-byte; no DLL was loaded/executed. Exact wheel origin is verified, while corresponding source/build and license analysis remain outstanding.

## yt-dlp binary

Local packaging/tools/yt-dlp.exe: 17840399 bytes; SHA256 `66674953fe251b89f4d08c5f0e35e0728679bd67ab3d7d05c0562af101dd3e7a`; NotSigned. This exactly matches the digest and size returned by official public GitHub release API for [2026.08.19](https://github.com/yt-dlp/yt-dlp/releases/tag/2026.08.19). Notices identify this version, but build does not currently enforce that digest. Frozen worker uses the executable; source worker uses Python yt_dlp. Both paths need matching version policy.

## Model provenance

worker/download_model.py pins Systran/faster-whisper-base revision `ebe41f70d5b6dfa9166e2c581c45c9c0cfc57b66` and fetches four allowlisted files with token=False. The [immutable upstream model snapshot](https://huggingface.co/Systran/faster-whisper-base/tree/ebe41f70d5b6dfa9166e2c581c45c9c0cfc57b66) declares MIT. All four source and dist files match upstream: model.bin via upstream LFS SHA256; remaining files via hash of bytes retrieved from exact-revision URLs.

| File | SHA256 |
| --- | --- |
| config.json | 56a6d8110d311f19c8f0471e562832c7527f146b567275bfca59fcf7c184da9a |
| model.bin | d01c3014881c9c6f3133c182f3d2887eb6ca1c789a7538c5c007196857a0a6a9 |
| tokenizer.json | fb7b63191e9bb045082c79fd742a3106a12c99513ab30df4a0d47fa6cb6fd0ab |
| vocabulary.txt | 34ce3fe1c5041027b3f8d42912270993f986dbc4bb34cf27f951e34a1e453913 |

Pin revision **and file hashes**, and include upstream model card/conversion provenance plus OpenAI Whisper MIT license in release materials. Existing allow_patterns omits those notices.

## Build and dependency lock gaps

Root requirements.txt is hash-locked and binary-only, but worker/requirements.txt has only six direct version pins and no hashes or transitive lock. Root lock omits key worker/build packages. Inspected venv contains faster-whisper1.2.1, CTranslate2 4.8.2, onnxruntime1.31.0, tokenizers0.23.3, numpy2.5.4, huggingface-hub2.2.0, PyAV18.0.0, PyInstaller6.22.3, hooks2026.8, altgraph0.17.5, pefile2024.8.26, setuptools84.0.0, pip26.2.1 and additional transitive packages. Python pin is 3.12.14. No complete reviewed worker/build artifact lock was found.

build-companion.ps1 checks only root requirements syntax/names/versions. It does not compare installed package inventory or wheel hashes, validate worker/build lock, verify FFmpeg/yt-dlp/model hashes, or require source completeness. companion.spec copies mutable PATH FFmpeg. Packaging content audit only checks forbidden names/extensions; it is not SBOM, provenance, signing, malware or source-license verification. Manifest hardcodes signed=false and version0.2.7-beta. THIRD-PARTY-NOTICES still says 0.2.4-beta. Compiler executable origin/version/hash also needs a pinned verified build record before execution.

## Minimal free release plan

1. Generate reviewed hash-locked worker and build dependency files for the target CPython3.12/Windows x64 environment, including all transitive dependencies and build tools. Install into a clean environment from verified wheels; assert exact inventory against locks.
2. Replace PATH copying with explicit project tooling paths selected by a reviewed provenance manifest. Fail build if media/model/compiler/version/size/hash mismatches. Pin verified official yt-dlp digest above and all four verified model hashes. Verify Gyan archive and extracted executable hashes before running a binary.
3. Complete **both** Gyan and PyAV corresponding-source inventories and notices before public redistribution. Preserve exact source commits, all included library source versions, license texts, patches and build scripts in a downloadable release source archive, with hash and stable public availability. Preserve installed Gyan README. If exact sources cannot be established, choose a reproducible reduced FFmpeg build using free tools and adapt PyAV to a matching reviewed build; this requires compatibility testing and is not a trivial license-only change. Do not assume the currently available master sources correspond to old binaries.
4. Update notices/license collection, include PyAV notice and underlying DLL licenses, model card/license, Python and other bundled licenses, and record complete SBOM/toolchain inventory. Add a single release version source. Generate manifest from measured artifact and Authenticode status after build/signing, not hardcoded assertions.
5. Run focused cancellation, preview-revocation, reconnect, capture timeout, source-rejection and packaging/provenance tests, then rebuild from fixed source only after provenance inputs pass. Run dependency checks and static security scanning using free tools. Do not describe source-process tests as installed/frozen acceptance.
6. Perform clean Windows VM install → launch → handoff → authorized test-media capture/transcription/render → cancel/delete/revocation → reconnect → upgrade/uninstall checks. Record artifact hash, environment and outcomes. Free local VM options depend on installed OS capabilities; use a disposable VM rather than executing the old installer on the personal machine.
7. Signing remains pending unless the user supplies access to an existing legitimate signing credential outside inspected stores. Any paid identity certificate/service requires user approval. Keep public signed-production gate closed; free internal QA can proceed after verified provenance without calling it trusted public signing.

Suggested commands after locks/provenance verifier and clean build environment exist: run `python -m pip check`; `python tools/dependency_policy.py`; `python -m pytest -q`; `python tools/verify_release_inputs.py`; `powershell -NoProfile -File packaging/build-companion.ps1`; `python packaging_audit.py packaging/dist/ClipBotCompanion`; inspect Get-FileHash/Get-AuthenticodeSignature on final installer and companion. The proposed release-input verifier does not exist yet. These are a plan, not executed acceptance evidence.
