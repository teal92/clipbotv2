# Live scout pipeline acceptance - 2026-10-11

Implementation is ready for private owner acceptance. Automated checks and local browser verification do not prove live capture or provider delivery. No real stream, paid model call, or provider upload has been performed during implementation.

## Owner flow
1. In Render, deploy the current `main` commit and wait for Live. Keep the existing service secrets and stable token encryption key; no new platform keys are required.
2. Install the Windows beta `packaging/dist/ClipBotCompanionSetup.exe` once. It includes the local runtime/tools/model and launches into the tray without a terminal. Choose Start with Windows only if you want it. The old .cmd file is a development fallback, not the customer flow.
3. Sign in to https://clipbot.your-domain.example and click Start ClipBot. If not paired, use Connect installed companion, then Open ClipBot Companion. Approve the browser app-opening prompt. Manual one-time-code fallback is available through the tray Connection status page. No social or AI secret belongs in the companion.
4. In Davey, acknowledge beta feedback and choose a non-paused usage preset. The account needs active plan coverage; free/test preference selection does not activate it.
5. In Streamers, save two scout slots. Find real live channels. Exercise Force monitor, online/offline favorites, and category selection within the plan's limits. Forced channels take priority, online favorites follow, and remaining slots rotate through live category matches. Offline channels use no capture slot.
6. Enable the owner Davey test for one hour, then use the header Start ClipBot. Wait for Running acknowledgment. Header Stop ClipBot cancels scouting while leaving the companion in the tray. The test has a $0.05 cumulative monthly analysis scope ceiling, subordinate to existing plan/global limits. Enabling it does not publish anything.
7. Watch Processing for actual concurrent capture and local resource metrics. Each capture window is bounded to about two minutes. Completed media is transcribed locally; Davey selects a bounded 15-60 second candidate. Empty/invalid results are not invented.
8. In Clips, review the real candidate, score, and rationale. Approve it to trigger local vertical rendering. Then preview the result in Publishing.
9. Review title/caption, confirm permission to publish, and choose a destination. TikTok also requires current creator/privacy/interaction settings. Publish first to Facebook, then separately to Instagram/TikTok. Uploaded is not Published: only a verified provider receipt counts.
10. Confirm the post in the actual social account, capture its receipt, and check Usage/owner metrics. Stop monitoring and pause the test when finished.

## Acceptance record
- Test forced/favorite/category selection, offline favorites, concurrent two-stream capture, and cancellation.
- Confirm collect -> local transcript -> Davey -> review -> local render -> queue -> direct upload -> verified receipt for the same real clip ID.
- Restart the worker: abandoned capture slots expire; completed owned previews restore only when hashes match. In-progress safe jobs resume after the old lease expires (up to two minutes). Uncertain paid analysis/upload outcomes are never automatically repeated.
- Revoke the worker and confirm capture stops and local previews disappear. Re-pair through the same customer flow.
- Only after the two-stream test stays healthy, measure four simultaneous captures for five minutes. Observe local CPU/memory/disk separately from owner server request latency/errors. One owner's test does not establish public multi-tenant capacity.
- Confirm budget stop, inactive coverage, cancelled leases, cross-account access denial, and duplicate publication behavior with automated checks; record real provider restrictions separately.

## Local prerequisites (already installed on the owner's computer)
Root Python dependencies plus worker/requirements.txt, FFmpeg/ffprobe, and the pinned local Whisper base model. For a fresh computer: create .venv, install requirements.txt and worker/requirements.txt, install FFmpeg/ffprobe from their official source, then run `.venv/Scripts/python.exe -m worker.download_model`. Root Render dependencies exclude local media packages.

Local pairing is stored with Windows DPAPI for the signed-in OS user and service origin. Model/media stay under ignored worker/data. Keep the worker running while monitoring, rendering, previewing, or uploading. Closing the worker interrupts captures; ambiguous uploads need status reconciliation rather than another upload.

Current implementation uses transcript-based selection and verified center-crop vertical output with burned subtitles. Chat velocity, visual face tracking, and automatic unattended publication are separate improvements. Public signup, platform app reviews, production database migration, recovery/MFA, and backup acceptance remain separate launch gates.

## Companion release gates
The owner beta installer is built locally and has been tested independently of the developer checkout: bundled FFmpeg/ffprobe/model readiness, actual model load, registered tray, and single-instance launch. It is unsigned. Public Download intentionally stays unavailable until an approved binary URL/version/SHA-256 is configured and corresponding-source/license redistribution obligations are complete. Private GitHub source stays private. Windows only at this stage. The build compiler is pinned to Inno Setup 6.4.3, which permits commercial use without purchasing a new license.

Website states are Offline, Ready, Starting, Running, Stopping, and Needs attention. Healthy heartbeat expires after 90 seconds. New Start/Stop intent must be acknowledged for its exact configuration revision. Transient networking retries with bounded backoff; revocation halts processing. Missing tools retain a health-only heartbeat and actionable repair message. Quit holds singleton ownership until local processing finishes.
