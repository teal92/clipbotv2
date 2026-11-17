# Native companion acceptance — 0.3.0-beta.1

The Apple Silicon package passed automated native acceptance. No native customer installer has been published yet, and real desktop installation/pairing remains unverified. Windows 0.2.10 remains independent.

## Evidence required for each target

- Exact committed source, installer SHA-256/size, target processor, minimum OS and installed runtime version agree.
- Pinned runtime, dependency closure, model, native tools, source archives and license notices pass verification.
- Extracted/copied package contains no credentials, customer media, unsafe links or unexpected native architecture.
- Actual bundled FFmpeg accepts the disposable trusted localhost certificate and rejects untrusted certificates and wrong hostnames. Unrelated I/O failures cannot satisfy rejection checks.
- Frozen application loads its local model, exercises VAD/transcription on synthetic media, extracts a rolling clip and renders a verified vertical preview. Offline model operation is required; no Claude calls or social posts.
- Mac DMG contains the application at its root and the copied application runs after unmounting the image. Linux package layout and required system libraries are inspected separately.
- Real desktop installation, secure pairing, browser application links, tray controls, startup preference, update and uninstall are recorded on the declared OS/processor. Headless checks do not prove these.

`tools/accept_native_companion.py` performs the automated package checks and emits a report. Its `cleanMachineAccepted`, `cleanInstallPairedAccepted` and `publicReleaseApproved` fields remain false. Failures produce no passing report. Actual desktop acceptance and release authorization are separate.

## Current status

| Target | OS storage/lifecycle probe | Source runtime | Prebuilt dependencies | Packaged acceptance |
| --- | --- | --- | --- | --- |
| Apple Silicon Mac | Passed native CI | Passed native CI | Passed native CI | Automated checks passed, run 39313855193; real desktop pending |
| Intel Mac | Passed native CI | Passed native CI | ONNX Runtime source build still required | Pending |
| Ubuntu/Mint x86-64 | Passed native CI | Passed native CI | Passed native CI; source desktop bindings passed run 39315503714 | Full package build running |

Mac packages have no verified Apple Developer ID and are not notarized. The owner approved an experimental public beta after review, without a tester email allowlist. This does not constitute manual desktop acceptance. The new native-only release manifest explicitly preserves both manual acceptance flags as false, requires provenance review and passing automated package checks, and discloses the pending desktop checks before per-artifact customer acknowledgement. Existing Windows acceptance rules remain unchanged.

Native artifacts use the existing public `YOUR-GITHUB-USERNAME/ClipBotV2-setup-guide` repository's releases to avoid paid server storage. ClipBot retains normal authenticated/email/policy/beta-acceptance gates. The server admits only a configured fixed asset ID in that repository, matching the reviewed target filename, version tag, SHA-256 and size, then redirects to GitHub's short-lived asset URL. No GitHub credential is stored on the website. Release binaries are public once published; running the companion still requires its normal account, pairing, worker lease and paid coverage checks.

The final whole-branch independent code/security review is required before public promotion. Intel and Linux must remain unavailable until their own packaged checks pass; an Apple Silicon pass cannot authorize another target.
