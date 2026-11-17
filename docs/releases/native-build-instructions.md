# Native companion build status and operator instructions

October 19, 2026. These are developer instructions, not a customer download announcement.

## Release tracks

Windows remains on the released 0.2.10 installer. Initial Mac and Linux candidates use 0.3.0-beta.1 and carry target-bound runtime metadata. Never replace the released Windows artifact, tag, or version with these new binaries.

Targets: macos-arm64, macos-x86_64, linux-x86_64. The two Mac packages cover Apple Silicon and Intel. Initial Linux desktop scope is Ubuntu 24.04/26.04 LTS and Linux Mint 22.x. Minimum macOS version is a build candidate of 14.0, not a published compatibility guarantee; inspect every bundled Mach-O binary and complete native acceptance before advertising it.

## What is implemented

- OS identities and native bundled-tool naming.
- Native protected credential adapters, per-user startup, single-instance locking and application URL handling.
- Independent per-target download snapshots and required versions, preserving legacy Windows reports.
- Website OS/processor selection, native notices and artifact-specific acknowledgements.
- Input hash/source/lock/model verification, native candidate package recipes and architecture/minimum-OS inspection.
- A manual native integration workflow with read-only repository permissions, pinned official actions, 45-minute job limits and one-day probe artifact retention.

## What is not yet accepted

No Mac or Linux customer installer has been built or published. The corresponding-source inventories and complete native Python dependency locks still need preparation and review on native hosts. Native Keychain/Secret Service, POSIX locks, one-time handoffs and hostile-link rejection passed on Apple Silicon, Intel and Linux runners. Actual Apple URL events, tray behavior, packaged media processing and clean installation remain acceptance gates.

The policy files macos.json and linux.json are build policies, not completed input inventories. The build script deliberately refuses to run without each target's reviewed .inputs.json, .lock and .approved.json and matching files. Do not bypass this check or substitute a Windows wheel, DLL, executable or source receipt for a native build.

PyAV must be built against the controlled decoder profile. Reuse the reviewed vcpkg registry c52f7bd748185ef0e0daf033d9f2ddfc8a3449ea and PyAV source 54a4395bb4cdd9cdd53ff6216c50b69f6475c13d as source inputs, then record the actual native compiler, recipes, dependencies, corresponding archives and binaries. The Windows build receipt does not attest to Mac/Linux output. Native FFmpeg renderer support must include the existing x264/libass features.

Mac tray integration introduces the documented PyObjC dependencies of pystray; Linux tray integration needs verified desktop/GObject/AppIndicator packaging or proven compatibility on the supported desktops. Resolve and review these dependencies before declaring the native lock complete. Native wheels existing on PyPI is availability evidence, not acceptance of all their bundled libraries.

## Free runner checks

The owner account's GitHub billing UI showed GitHub Free, 0 of 2,000 included Actions minutes used, 0 of 0.5 GB storage used, and an account-wide $0 Actions budget with paid usage blocked. Check again before later dispatches; never raise a budget to make a job run.

GitHub requires a workflow_dispatch definition on the default branch. The owner approved publishing only the manual workflow and free native checks. That workflow is registered on main; application feature source remains isolated. Later workflow-only changes retain the same manual/read-only/no-production-secret restrictions. Dispatch checks against the full reviewed feature commit hash. Use macos-15 for ARM, macos-15-intel for Intel and ubuntu-24.04 for Linux. No production credentials are provided to these jobs.

The Linux probe installs desktop keyring prerequisites only inside its disposable GitHub VM and starts a disposable D-Bus/keyring session. This is not a privileged service installation on the customer's computer. Test passwords/tokens are freshly isolated from production and never become application credentials.

## Native build command

On the matching host, with clean committed source, reviewed CPython 3.12.15 and the exact native input inventory prepared:

    python packaging/build-native.py --target macos-arm64 --output /absolute/new/output-directory

Substitute macos-x86_64 or linux-x86_64 for other hosts. Use a new output directory. The command refuses wrong hosts, modified inputs, unreviewed dependencies, unsafe bundle content, incompatible native binaries or an overstated minimum OS.

Generated manifest status is internal, unsigned, not notarized, provenance-unaccepted and clean-machine-unaccepted. Those are accurate initial states; a successful package command must not automatically flip them. A complete build/source audit and actual desktop acceptance are required before promotion. Initial unsigned Mac beta distribution needs approval of the specific package and warning.

## Real-device acceptance

The waiting Mac customer is the first Mac beta tester. Collect processor/OS, fresh install, launch, pairing, Start/Stop, processing, restart and upgrade results without private pairing codes, tokens or customer media in public reports. Test both Mac architectures and each advertised Linux desktop family before claiming their coverage. CI integration probes do not establish clean installation, browser handoff or tray acceptance.

Before any public download promotion, check delivery capacity: the production Render disk is small and already holds current/rollback Windows releases. Keep independent rollback receipts and do not fill that disk with three additional large packages.

## Reviewed runtime source build

Native candidates now pin CPython 3.12.15 (September 30 security release), OpenSSL 3.5.9 and libffi 3.5.2. Windows remains pinned independently to its released runtime. Exact upstream archive URLs, sizes and SHA-256 digests are in packaging/platforms/runtime-sources.json. Python's digest was checked against python.org; OpenSSL/libffi digests and sizes against their official GitHub release assets. All three actual archives passed local hash verification and restricted extraction.

On a disposable matching native host:

    python3 tools/build_native_runtime.py --target macos-arm64 --output /absolute/new/runtime-check

The command builds into the new directory without replacing system Python, using a maximum of four compiler jobs. Source archives, configuration logs, build log, source pins, command list and actual compiler/SDK receipt remain available for review. No production credentials or paid API calls are needed. The manual workflow runtime mode performs this check with one-day diagnostic artifacts; it does not publish customer downloads. Hash/source checks and module diagnostics do not constitute full packaged-app acceptance.

Native integration evidence: Linux run 39291568132, Apple Silicon 39291986138, Intel 39291988822. All passed; desktop and clean-machine acceptance are explicitly false in those receipts. Latest source checkpoint before runtime bootstrap: 1,010 backend tests passed, four native-only checks skipped on Windows; 240 frontend tests passed.

## Native media and dependency preparation

Source-runtime checks passed on both Mac architectures (runs 39293419546 and 39293422701). Linux compilation requires distro compression/database development headers; missing headers fail the module check. These build-machine prerequisites are recorded separately from release-approved bundled inputs.

The native-renderer profile adds OpenSSL and FFmpeg version3 explicitly for HTTPS capture. The released Windows renderer profile stays unchanged and uses its Windows TLS support. tools/build_native_media.py uses the reviewed immutable vcpkg baseline, separate dynamic decoder/static renderer installations, matching architecture, and a candidate Mac OS floor of 14.0. It checks FFmpeg version, HTTPS, H.264 and subtitle support and records hashes/licenses/actual package metadata for later source review. Successful compilation never marks corresponding sources or customer acceptance complete.

Native package intake uses tools/native_dependency_snapshot.py. It reads official PyPI metadata only, matches package identity/version/processor/OS floor/Python ABI, checks artifact origin/hash/size, and refuses unknown/conflicting dependencies. It installs nothing and never produces an approved release lock. PyAV must still use our controlled source commit; its PyPI source metadata is comparison evidence, not permission to substitute a vendor build.

The companion upload URL validator now lives in clipbot_common, shared identically with the server, avoiding unnecessary server-auth/billing code and cryptography dependencies in the native application. Intel still needs an independently built ONNX Runtime 1.31: upstream publishes its current Mac wheels only for Apple Silicon. Do not substitute a discontinued version or remove speech filtering to make the Intel build pass.

Native source runtime checks have now passed all three targets: Apple Silicon 39293419546, Intel 39293422701, Linux 39294599652. The Linux rerun includes its required build headers. Exact compilation/module output was downloaded and checked. Backend checkpoint after upload isolation: 1,035 passed, four OS-only skips.

Committed target .dependencies.json files are artifact review evidence, deliberately marked incomplete and unapproved. tools/install_native_wheels.py prepares an isolated build environment from these exact records: it checks policy/closure/target/ABI again, verifies downloaded bytes, uses offline hash-required pip without automatic dependency resolution, and checks the installed inventory. Pending source packages remain explicit and no release lock or public acceptance is generated. The helper uses ensurepip's vendored parser only before the reviewed packaging module is installed. The manual wheels mode first builds the pinned native runtime, then checks prebuilt dependencies; this still does not build or publish a companion.

## Decoder and TLS evidence

Apple Silicon media compilation passed in run 39298222595 after isolating pkg-config search and choosing Apple's Core Text font provider explicitly. Source-runtime build trust now copies the native build host's valid public CA bundle into the private OpenSSL prefix, recording its digest; no operating-system trust store is modified and peer/hostname verification stays enabled. Apple Silicon offline prebuilt dependency checks passed in 39300951800.

Source-built decoder preparation uses tools/build_native_pyav.py with the reviewed PyAV commit and the checked decoder prefix. It refuses other prefixes, changed decoder inputs, unreviewed wheel identities or OS floors, repairs bundled libraries, installs only the locally hashed wheel and verifies installed bytes. The final native input gate requires packaging/tools/native/TARGET/wheels/av-reviewed.whl; a version string cannot substitute for that artifact. The decoder workflow mode combines these stages without publishing a companion.

Native stream capture explicitly requests TLS certificate verification and packaged certifi roots; Schannel uses Windows trust. Exact FFmpeg 8.1.2 OpenSSL source includes hostname verification, despite the warning in generic documentation. Packaged local wrong-issuer/hostname tests remain an acceptance gate. Latest full backend checkpoint: 1,068 passed, four OS-specific skips; no customer installer accepted yet.

Apple Silicon controlled decoder compilation and wheel repair passed in run 39305311427 from source d935740; the installed decoder bindings and libraries matched the reviewed wheel bytes. Evidence is in docs/evidence/2026-10-19-macos-arm64-decoder.json. Full internal installer assembly and packaged acceptance are still pending. The workflow expansion for retaining an internal candidate requires the pending owner approval after automatic approval review treated the earlier permission as checks only.
