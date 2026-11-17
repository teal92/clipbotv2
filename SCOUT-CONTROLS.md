Scout workspace update

Twitch and Kick have separate compact live directory panels, with internal scrolling.
Automatic selection uses live viewer counts, with explicit streamers then one top live streamer per forced category, favorites, and remaining ranked sources.
Kick top categories are ranked by aggregate viewers within the returned live-stream directory, rather than a claimed platform-wide total.
Scout controls store account-owned local capacity (1-8), capture windows (30-300s), playable-window quality gates, candidate sensitivity (60/75/90), and clip range limits (15-60s).
Companion 0.2.1-beta is required for monitoring starts and captures new windows using saved controls. Existing captures finish using their original settings.
Owner beta feedback must be acknowledged explicitly. Paid analysis remains a bounded one-hour owner test with a $0.05 ceiling; no automatic acknowledgment or activation.
This implements window-completeness quality and score/length acceptance. The v1 acoustic spike/pre-roll/post-roll detector and freeze grading are not ported by this update.

## Scouting visibility
Streamers shows simultaneous streamer/category lists for both platforms. Scouting uses account-owned capturing jobs updated within 90 seconds, not a requested Start flag, to show active streams. Current watch time starts at job creation; collected counts include ready/published clips among the latest 100 jobs. These are not lifetime totals.
Previews are provider-hosted and load only when opened. Polling preserves mounted players. Twitch embeds follow its parent parameter and 400x300 minimum: https://dev.twitch.tv/docs/embed/video-and-clips/ . Kick player settings: https://help.kick.com/en/articles/8010826-how-to-embed-your-kick-livestream . Preview traffic is on the browser's connection.
Save and Start confirm their outcomes. Start persists selected controls and slot count before the existing guarded companion start. Unsaved control drafts no longer stop status polling.
