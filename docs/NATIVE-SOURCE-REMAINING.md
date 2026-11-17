# Native source investigation — 2026-10-14

`packaging/source-inventory.json` is an incomplete evidence inventory, not a complete source delivery or redistribution certification. All 15 recorded component/tool source archives were downloaded into the separate evidence directory and independently matched the immutable recipe SHA256 values. Archive path inspection found no unsafe member names. No archived source scripts, vendor media DLLs or generated ClipBot installer were executed. The authenticated compiler installer subsequently ran only in the documented isolated portable mode described below. The existing compiler help command and its official standalone signature-verification tool were run after executable origin/signature checks. No credential or customer content was inspected.

The separate binary-origin checks remain those recorded in [the companion audit](COMPANION-PROVENANCE-AUDIT.md). Exact wheel/binary matches establish origin; they do not establish matching modified source, license fulfillment or clean-machine acceptance.

## PyAV: progress and exact gaps

The [immutable vendor package recipe](https://raw.githubusercontent.com/PyAV-Org/pyav-ffmpeg/a71bf9279f7a4659154b68ba6783e89be460bcd5/scripts/pkg.py) supplies archive URLs and expected digests. The inventory records 14 Windows x86_64 component/header archives and one NASM tool source entry. All 15 expected SHA256 values matched the downloaded archive bytes. Version/tag URLs can be mutable; the expected digest is essential. Linux-only GnuTLS/ALSA dependencies are excluded from the Windows selection.

The [build selection script](https://raw.githubusercontent.com/PyAV-Org/pyav-ffmpeg/a71bf9279f7a4659154b68ba6783e89be460bcd5/scripts/build-ffmpeg.py) and [builder](https://raw.githubusercontent.com/PyAV-Org/pyav-ffmpeg/a71bf9279f7a4659154b68ba6783e89be460bcd5/scripts/cibuildpkg.py) expose additional unresolved inputs: historical fetched configuration helpers, copied compiler-runtime DLLs and installed build tools. Exact versions and matching source packages must be recovered from original CI records/cache or upstream attestations. Current packages cannot prove historical correspondence.

The [exact FFmpeg patch](https://raw.githubusercontent.com/PyAV-Org/pyav-ffmpeg/a71bf9279f7a4659154b68ba6783e89be460bcd5/patches/ffmpeg.patch) changes configure categorization of x264/x265. License review must cover actual library terms, linkage and notices; this patch is not a licensing exemption. The builder applies any matching package patch, so the entire patch directory must be captured and reviewed. License-file names and hashes were captured from the archives without extracting or executing them. License and linking obligations remain unresolved; identifying a license filename does not establish redistribution compliance.

The [README at this vendor commit](https://github.com/PyAV-Org/pyav-ffmpeg/tree/a71bf9279f7a4659154b68ba6783e89be460bcd5) names a different x264 commit from `pkg.py`. The inventory uses the recipe commit and flags the discrepancy; neither alone proves which source produced the shipped DLL.

Practical next steps:

1. Completed acquisition: 15 archives independently hash-matched in the separate evidence directory. Continue treating build scripts as untrusted data.
2. Captured pinned vendor/PyAV source archives: 19 and 278 file contents respectively matched upstream Git blob entries, including all five vendor patch files. The vendor output archive 8.1.2-1 was hash-verified. All 25 shipped DLL executable code sections match that output; 11 match full bytes. The remaining 14 now also match full-byte static reconstruction limited to actual dependency names, original zero-padding writes, import name pointers, exact section-size extensions and independently recomputed PE checksums. No unexplained bytes remain. Destination name locations were observed from the wheel; this does not independently reproduce delvewheel allocation or name-hash algorithms and does not establish source/license completeness. The wheel records delvewheel 1.13.0 and its repair arguments, providing a concrete next investigation step.
3. Recover the Windows CI package inventory and historical runtime source packages, fetched helpers and tool versions. Record linking relationships and any license exceptions from exact source materials.
4. Assemble a complete hash-verified source package with stable public availability alongside release evidence. Keep the existing source-completeness gate closed until that package and correspondence review are complete.

## Gyan: upstream evidence or replacement required

October 15 follow-up located two successful Windows x64 jobs for the exact
vendor revision (runs 28393781929 and 28139818759). Their public artifact lists
were empty and log API requests returned 403; no historical runtime/toolchain
package inventory was recovered. This narrows the evidence search but does not
establish source completeness or prove those logs were deleted.

The [9.0.1 release](https://github.com/GyanD/codexffmpeg/releases/tag/9.0.1) identifies FFmpeg commit `bf1b838f2a`. The [tag's repository tree](https://github.com/GyanD/codexffmpeg/tree/9.0.1) contains the support/mirror README and `.github`, with no complete build recipe located. The [build site](https://www.gyan.dev/ffmpeg/builds/) gives variants and library lists; it does not establish exact historical source modifications and full build environment. A generic source-code archive of the support mirror is insufficient.

Preserve the original binary distribution README and its exact library versions/commits, then obtain matching archives, patches and scripts plus historical toolchain evidence from upstream. No upstream contact was sent. If that evidence cannot be recovered, replace standalone FFmpeg with a build whose full source recipe is controlled, archived and reviewed. Separately replace/rebuild PyAV's native dependencies if its own historical gaps remain. Removing only standalone FFmpeg leaves PyAV DLLs in the package.

Replacement is a compatibility change: verify harvesting, probing, Whisper decode/resampling, H.264/AAC output, crop/scale/subtitle rendering, preview playback, cancellation and clean Windows installation using authorized synthetic/test media. Preserve full reproducible build/source evidence for the replacement. Listing source links alone does not meet this release requirement.

## Build verification and installation still pending

The clean build environment now contains exactly 64 approved hash-locked distributions, including pip 26.2.1, on CPython 3.12.14 Windows x64. Build verification rejects alternate CPU targets, extra distributions and unlisted compiler support or license files. This does not authorize a native release.

The official Inno Setup 6.4.3 installer SHA256 matches its immutable release asset evidence and has a valid Pyrsys B.V. Authenticode signature. It was executed in its documented portable/current-user mode into a new isolated folder, without changing the existing installation or file associations. Seven compared core components, including unsigned Setup.e32 and SetupLdr.e32, exactly match the previous compiler. All 33 top-level support files are now staged and hash-pinned. A synthetic, explicitly non-release installer compiled successfully; it was not run. Compiler origin and this smoke check are complete. A real ClipBot installer has not been built or clean-machine accepted during this pass. Windows Sandbox is unavailable on this computer; a separate Windows test environment is still needed. The sourceComplete flag remains false.
