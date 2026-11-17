# Continuous scouts implementation plan

Approved intent: users configure streamer phrases, voice excitement, chat phrases and chat spikes; scouts keep watching while bounded clips process. Preserve footage before and after a cue. Counts are allocated per service and Streamers exposes compact controls.

Architecture: local continuous ffmpeg segments form a bounded rolling buffer. A local trigger engine combines selected cues with a cooldown. A trigger opens an owned worker job only when processing capacity exists, preserves the requested range and submits one bounded recording to the existing transcript/Davey/review pipeline. Snapshot/live UI stays the same size. Monitoring heartbeat lists real sources separately from clip jobs.

- [x] Validate and persist account-owned trigger rules and timings; expose editable controls.
- [x] Implement bounded chat input and cue evaluation; document unsupported provider capabilities explicitly.
- [x] Implement continuous local buffer, retention, exact clip range, disk/cancellation safeguards.
- [x] Report real monitored streams and per-platform states; maintain bounded processing queue without stopping monitoring.
- [x] Keep preview-before-approval isolated from publishing and paid analysis.
- [x] Test cue selection, cooldown, timing, queue recovery, allocation, restart and ownership; run real local media smoke.
- [x] Build one companion update, host private installer, deploy verified changes.

Ruling: default clip timing is 20 seconds before and 20 after, editable within a total of 60 seconds. Audio excitement identifies a candidate only; Davey remains the bounded review gate. Kick chat needs supported event permission and webhook setup; never claim its cues are active without a verified feed.

Ruling: requested scout count remains the single user capacity setting, as explicitly requested. The legacy hardware_slots constructor is retained for older callers but does not impose a second hidden limit. Extraction is capped at four in flight and two CPU workers. Shutdown runs queued extraction cleanup instead of cancelling its futures. Speech cues preserve the sampled segment time, not transcription completion time.

Verification: real recorded media extracted 40.02 seconds from continuous segments; frozen companion model, transcription, rolling extraction and candidate preview passed. Backend and frontend suites run before release. Kick chat implementation remains explicitly gated until its app webhook is configured; Twitch read-only chat requires customer reconnect consent. Both integrations were explicitly approved in chat after an automatic-review scope rejection.
