# Live scout-to-publish integration — revised design for review

## Outcome and existing state
Run real Twitch/Kick scouts concurrently, discover a clip-worthy moment from a monitored live stream, ingest it, transcribe locally, perform budgeted Davey analysis, edit locally, enqueue and publish with verified delivery. Use the same website, paired worker and account authorization as customers. All five platform accounts have been connected by the owner, but that is not evidence of successful uploads.

The v2 worker currently implements pairing and heartbeats only. The service has encrypted account OAuth, scoped worker credentials, spending reservations, feedback and plan coverage. It does not have a worker execution queue, paid Claude dispatch adapter, rendered clip transfer, or social publishing integration. Existing v1 harvesting/rendering and upload code is reference material, not a safe drop-in: it uses global environment/configuration credentials and its own database.

## Chosen architecture and alternatives
Extend the v2 paired-worker design; retain existing modular vanilla frontend and Python service. This preserves customer-owned media processing and isolates accounts. Copying the complete v1 application would preserve incompatible global secrets and tenant assumptions. Moving processing to Render would incur media transfer/storage and processing costs and contradict the agreed architecture. Neither alternative is selected.

Start with bounded live monitoring, not a pre-created upload or manually substituted VOD. Exercise favorites, forced streamers, category scouting and concurrent monitors; carry one naturally discovered candidate through the complete pipeline before allowing more publishing. Facebook Page Reels is the recommended first destination because it avoids TikTok app-audit/private-post variables. Add Instagram and TikTok delivery checks after the same clip succeeds on Facebook. Customer selection controls which destinations receive each post.

## Customer flow
Connect Accounts remains the single place to pair the local worker. A local worker launcher opens a loopback-only setup screen, accepts the one-time code, and shows prerequisites and connection state; no customer developer keys. Media tools and models are checked before offering a test. Downloads are disclosed before installation.

The website Streamers screen is the test entry point. The owner selects real currently live Twitch/Kick sources through search, favorites and category filters. The worker captures bounded live windows and preserves source IDs, channel/category identity and source timestamps. Discovery and ingest must originate in that monitored stream; uploading an already-created clip or replacing an unavailable live source with a VOD does not satisfy acceptance. Failed/absent sources are shown honestly. No fabricated transcript, score, or source is substituted. A published candidate is 15–60 seconds.

Favorites are durable per-account preferences for prioritized sources. Forced streamers are explicit pinned live sources that take priority over normal rotation, subject to the same scout slots, permissions and safety stops. An offline pinned source is marked offline, reserves no active capture process, and is retried on a bounded discovery schedule; it does not prevent other eligible sources from using available slots. Force-monitor never means force-publish or bypass AI/clip limits. Forced sources precede online favorites; remaining slots are filled from selected category discovery with deterministic rotation and duplicate removal. If pinned requests exceed plan scout capacity, the website explains the limit before saving rather than silently ignoring a source. Favorite streamer/category counts are enforced using existing plan coverage. A source cannot occupy two slots merely because it is forced, favored and discovered in a category.

Begin with two simultaneous live sources, including Twitch and Kick when suitable authorized live content is available, then increase to four and subsequently the account scout limit only while hardware and server metrics are healthy. Each step uses a five-minute observation interval. Exercise a forced source, an online favorite, category-driven selection, an offline favorite, duplicate discovery and source stop/restart. Local CPU, RAM, disk, ingest bandwidth and backlog are measured separately from Render request latency, failures, memory and queue depth. These observations prove this owner run; they do not prove public multi-tenant capacity. Separate authenticated two-account/concurrency tests establish isolation and reservation behavior.

Discovery and monitoring controls use official provider endpoints where supported. Unsupported Kick category discovery must be disclosed as a blocker, not replaced with unreviewed endpoints or fictitious results. The selector never promises a live source is capturable until the actual ingest probe succeeds. Capture windows, transcription and rendering queues are bounded; when the render/analysis queue is full or disk headroom is insufficient, pause additional capture and show why. Stop Monitoring cancels capture promptly while preserving completed clips and receipts. No clip is posted simply because monitoring was enabled.

The local worker collects, transcribes with local Whisper and sends bounded timestamped transcript/context to server-side Davey. The service reserves a conservative token cost under existing global, account and review limits before one Haiku 5.5 request. No automatic provider retries, tools or model-generated executable commands. The account must have eligible coverage and an active spending preset. Initial test spending ceiling is $0.05, subordinate to all existing stops. Dispatch remains default-off until the adapter is implemented and verified.

Davey returns one validated candidate with a 0–100 score, in-window timestamps, rationale and bounded draft metadata. The normal threshold is 75. A below-threshold result does not silently publish; the user can explicitly approve a manual test candidate. Invalid model output fails visibly and billed usage is still reconciled.

The worker renders H.264/AAC MP4, 1080x1920, with local subtitles. Initial framing is a clearly identified center crop with preview; intelligent face/game layouts must not be claimed before implemented. Reuse reviewed v1 rendering routines where they can be isolated. Local preview, captions and destination settings appear before the user presses Publish. The first test creates exactly one post on one explicitly chosen destination.

## Interfaces and trust boundaries
Service job ownership is derived from the authenticated session or paired worker token, never a client-supplied user ID. Persist job stages, leases, cancellation, bounded errors, metadata and publication receipts. Candidate and clip IDs are durable. State transitions reject stale leases and cross-account access. Revoking a worker stops new leases and subsequent credential use.

Keep raw media on the worker. Only necessary transcript/context goes to the Claude request; it is not Big Davey contribution data. Existing beta evidence sharing receives minimized decisions/labels only. Do not store raw transcripts or videos in shared learning or service logs.

The service initializes official resumable publishing and reconciles status using the selected account's encrypted authorization. The worker uploads bytes directly to the provider, using an account/job-scoped upload grant. Where provider upload requires a Page token, deliver only the selected account's needed token to its authorized worker over HTTPS, in memory, never to website JavaScript or a configuration file. No developer app secrets, Claude key or encryption key leave the service. Validate provider-issued upload URLs against the documented HTTPS host/path scheme, prohibit redirects, and never forward a bearer token to an arbitrary host.

Worker local HTTP is loopback-only, rejects foreign Origins, and requires a pairing/session secret for file access; preview paths cannot escape the configured job directory. Commands use argument arrays with bounded timeouts, not shell interpolation. Source URLs are restricted to approved provider schemes/hosts; no arbitrary network fetch from the cloud service.

## Publication correctness and constraints
Authenticate destination ownership and obtain current provider capabilities before publishing. TikTok requires current creator-info, explicit upload consent and user-selected supported privacy/settings; development audit constraints remain visible. Meta uploads use official resumable flows and provider status confirmation. OAuth connection alone never sets publishingReady.

Reserve beta clip capacity atomically before publishing. Starter/Creator: 20 distinct clips per UTC day; Pro/Custom: no ClipBot posting cap. Cross-posts use one durable clip ID. Concurrent jobs cannot exceed the cap. Keep uncertain publication attempts pending and reconcile them before retrying; never repeat an upload solely because a response timed out. Failed confirmed attempts release reserved capacity. Only verified provider receipts increment publication totals.

## Files and implementation increments
1. Worker job/store/API boundary, persistent tenant-owned scout configuration and secure local launcher, extending worker/client.py, server/store.py and API routers; pairing, scout-slot, preference-limit and tenant-isolation tests.
2. Provider discovery, live monitor scheduler and local ingest/transcribe/render modules in worker/, worker-only dependency list and prerequisite checks. Favorites, forced sources, category rotation, source deduplication and backpressure are part of this increment. Existing v1 routines are individually reviewed before reuse.
3. Server Claude analysis adapter using BudgetLedger and official Anthropic SDK; bounded provider usage settlement and cancellation/uncertainty handling.
4. Account-scoped publication broker and direct-upload worker adapters, durable receipts and beta clip reservation enforcement.
5. Website live source search, favorites, forced streamer and category controls, scout start/stop, local preview handoff, queue approval and destination settings; actual stage status updates in Logs, Clips, Processing, Publishing and owner metrics.
6. Real concurrent live monitoring and full discovered-clip ingest-to-queue-to-post test, then the same reviewed clip tested individually on the other destinations. Live observation is required before claiming end-to-end success.

## Verification and acceptance
Tests precede each implementation: live source changes, category rotation, offline favorites, forced priority, slot over-allocation, duplicate source selection, bounded queue saturation and monitor stop/restart; expired/replayed pairing; wrong-account jobs/files/tokens; worker revocation during execution; local path traversal and hostile source/model text; provider redirect/host rejection; cancellation, crash recovery and disk exhaustion; invalid timestamps/output and below-threshold behavior; paid allowance/global stops and billed failures; lease races, duplicate callbacks, ambiguous provider responses and concurrent beta limits. Provider integration tests use injected transports; separate live tests establish actual media and publication behavior.

Acceptance requires demonstrated live scout selection, favorites/force/category behavior and concurrent monitoring under observed load, a real discovered source window ingested, a real bounded billed analysis recorded, a playable rendered preview, explicit publish approval, provider-confirmed post, and matching account usage/publication metrics. Record each tested platform separately. No live call, download, post or continuous monitoring was started while drafting this design.

## References
- Existing v2 worker/client.py, server/budgets.py, server/oauth.py and tests/test_worker.py.
- Existing v1 app/pipeline.py, app/clipper.py, app/transcriber.py and production publishing/uploader.py (read-only references).
- https://developers.tiktok.com/docs/en/content-posting-api-get-started
- https://developers.tiktok.com/docs/en/content-sharing-guidelines
- https://platform.claude.com/docs/en/models/haiku-5-5/overview
