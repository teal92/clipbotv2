# ClipBot — next beta update tracker

Updated October 19, 2026. Release candidate **0.2.10**, updating 0.2.9. Changes below are implemented and checked locally; public deployment and installer promotion are recorded in the release receipt after acceptance.

## Frontend — prepared
- Add Account → Patch notes, sharing the versioned history with the update popup.
- Rename customer-facing forced priorities to **Favorite streamers** and **Favorite categories**. Existing saved selections remain compatible.
- Add separate entry forms in each Twitch/Kick card; category lookup offers platform matches, and streamer lookup accepts existing offline channels.
- Keep removable saved lists with Waiting/Live/Monitoring evidence. Preserve unfinished entry forms during page updates; duplicate additions do not remove a saved favorite.
- Gold text marks favorite streamers/category assignments only. Ordinary scouts use white text. Remove special colored borders, outlines, backgrounds and platform accents from these scout cards/tables.
- Rename “recording now” to “monitoring now.” Local buffering does not mean a clip has been submitted to Davey.
- Keep prior normal-priority streamer preferences and category filters visible/removable so old configuration does not silently affect discovery.
- Keep offline favorites first in bounded metadata lookups without increasing the maximum batch size.

## Backend / companion — prepared
- Pause production monitoring when trigger settings are missing/malformed. Do not fall back to recurring timed capture/review.
- Preserve signal-triggered clips using saved before/after timing and cooldowns. Manual Clip now remains an explicit user-triggered exception.
- Keep a temporary, bounded local buffer for pre-trigger footage. Quiet buffering creates no review job or Claude analysis request.
- Favorite categories retain priority without excluding unrelated automatic streams while waiting. Explicit existing category filters remain respected.
- Report a safe trigger-settings attention state; reject starting until the companion reports ready.
- Classify the three existing public showcase JS/CSS assets as static resources so they do not consume anonymous account API quota. API request limits are unchanged.

## Verification
- Frontend: **235 tests passed**, including persistent history, tab selection and shared update notes.
- Full backend run: **960 passed, one failed**. The failure reproduced independently and identified the showcase static-resource classification issue above.
- After fixing it: **86 affected backend/security tests passed**, including the previously failing startup limit test, discovery, scout selection, triggers, companion controls and cue dispatch.
- Browser: Enter immediately reveals category matches; separate category/offline-streamer adds work; favorites are gold and automatic scouts white; shared neutral borders/backgrounds; no page overflow at desktop or 390px width.
- Independent code review found no remaining substantive blockers, including the final static-classification and bounded-lookup changes.
- Tests use synthetic accounts, mocked providers and local files. No real Claude requests, social posts or payments were made.

## Release checks still required
- Build companion 0.2.10 containing the safeguard. The installed 0.2.9 binary is unchanged by source edits.
- Run frozen-runtime and installer/update acceptance, verify pairing/data preservation and publish matching installer/manifest hashes using the existing release procedure.
- Deploy compatible server/frontend changes and verify hosted assets and attention-state handling. These changes are being held for the next patch.

## Already released separately
- Clearer companion Download / Connect / Open actions and one-click Copy code / Copied in both pairing screens.
- Obsolete sandbox billing webhook disabled. Live billing configuration left unchanged.
