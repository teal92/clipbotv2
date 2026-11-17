# Current hybrid plan and cost proposal
Updated 2026-10-10. This supersedes earlier plan proposals. Pricing, entitlements, Patreon verification and spend enforcement remain unimplemented.

| Plan | Price/month | Total Twitch/Kick scouts | Favorite streamers/categories | Candidate review policy | Internal monthly Claude cost ceiling |
|---|---:|---:|---:|---|---:|
| Starter | $7 ($5 verified creator Patreon) | 6 | 0 / 0 (proposed) | 15/day, 450/month | $2 |
| Creator | $25 | 12 | 3 / 3 | 45/day, 1,350/month | $6 |
| Pro | $60 | 30 | 10 / 10 | No fixed advertised allowance; fair-use throttling and spending stops | $12 |
| Custom | Quote required | Manually chosen | Manually chosen | Manually chosen; approved after cost review | Approved per quote |

Starter posting allowance: 3 posts per platform per day. Creator currently has the same allowance as a launch assumption; Pro posting remains subject to platform rules. Posting is a maximum allowance/target, NOT a guarantee of suitable clips or successful platform delivery. These differences need product review before selling.
Scouts are combined Twitch/Kick slots (3+3 or 6+0 for Starter). Favorite streamers prioritize scouts and do not add slots. Category favorites are priorities, not extra stream captures.
Custom UI drafts allow 100–10,000 reviews/month, 1–100 scouts, and 0–100 favorites of each type; streamer favorites cannot exceed scouts. These bounds are quoting limits, not approved paid entitlement. Save Custom Request stores a local draft and does not buy or activate anything.

## Hardware and service responsibilities
Customer hardware/local worker: stream monitoring, lightweight detection, local transcription, editing/rendering, media files, personal context and authorized media delivery. The customer's computer must be running and sufficiently capable. More scouts primarily increase their local CPU, bandwidth and disk demand.
ClipBot server: authentication, paid access, coordination, software updates, metadata and usage records, and secure Claude request mediation. No video/audio library storage or media relay on this server.
Davey is a personalized assistant built from local worker signals and user preferences. Claude is the paid remote reasoning model running at Anthropic; it is not installed or executing locally just because the worker runs locally. Local detection/transcription reduces the number of paid calls. Shared server-Davey feedback remains a consented aggregate-learning proposal; saving reviews does not train Claude model weights.

## Cost calculation
Current official Haiku 5.5 pricing for prompts up to 100K tokens: $0.10 per million input, $0.50 per million output.
Example bounded total per candidate review: 20,000 input + 2,000 output tokens across ALL calls in that review => $0.003, before any extra tools. Longer context, retries, more calls, captions/metadata requests and shared-Davey jobs must all be accounted for.
- Starter: 15 reviews/day x 30 days x $0.003 = $1.35/month. For a 31-day billing period, 450 monthly reviews can be exhausted before month end; use the lower daily/monthly entitlement.
- Creator: 45/day x 30 x $0.003 = $4.05/month. The $6 internal ceiling leaves headroom under these assumptions.
- Pro: at the same bounded rate, a $12 ceiling supports at most 4,000 reviews/month (about 133/day averaged over 30 days). No fixed advertised quota does NOT mean unlimited paid API calls or unlimited throughput. Throttle or pause at the real cost/token ceiling.
- Custom example: 2,000 reviews => $6 token cost under the example assumptions, not the customer's subscription price. Hosting/payment/support and safety margin are additional.

Three unique approved clips per day cross-posted to three social platforms => 9 posts/day from 3 clips. At five reviewed candidates per accepted clip, this needs 15 reviews/day. The acceptance rate is an assumption; rejected moments may mean fewer posts.
Three DIFFERENT clips per platform across three platforms => 9 unique clips/day; at the same acceptance ratio this needs 45 reviews/day and $4.05/month example inference cost. That is a much tighter margin at $7, before payment fees, account hosting or support. Do not promise 9 distinct clips/day in Starter without measured evidence or repricing.
100 Starter accounts at full example use => $135/month inference, not a total $2 cap. 100 Pro accounts at their proposed individual $12 ceilings => $1,200/month exposure. User caps alone cannot prevent a surprise aggregate bill.

## Preventing surprise bills before launch
- Proposed launch-wide Claude cap: $75/month as a planning placeholder, separate from hosting. Owner must choose the real amount. Reserve worst-case token costs atomically BEFORE every job and retry; include per-user, per-job, daily, monthly and global ledgers. Stop dispatch when reservations would exceed any applicable budget.
- Bound input/output tokens across all passes; no automatic expensive-model fallback. Include system prompts, tool messages, metadata/caption work and shared-Davey requests in billed cost accounting.
- Cap queue sizes, concurrent inference, retry count and retained context; deduplicate jobs. Never bill based only on "finished clips" while analyzing rejected candidates for free.
- Begin with fixed-size hosting and autoscaling disabled. Bound API response sizes, rate-limit authenticated users and abusive signups, and configure provider usage alerts/actual enforced limits where supported.
- Verify service/database/email/bandwidth prices before provisioning. A server notification or frontend preset is not a provider billing stop. API/metadata traffic is still billable even with all video local.
- Restrict beta capacity until actual 6/12/30-scout metadata cadence and model quality/cost are measured. Define transparent fair-use/customer recovery terms for a global spending pause; do not sell throughput that the global cap cannot sustain.
These are required designs, not implemented billing protection. No fixed total bill guarantee or profitability claim is made.

Sources checked 2026-10-10:
- https://www.anthropic.com/claude/haiku
- https://render.com/docs/outbound-bandwidth

Order: finish pricing review -> website/authentication/server/hosting -> Davey integration.

## Custom sliders and price equation (current)
Custom controls now use ranges: scouts 0–40; favorite streamers 0–25; favorite categories 0–25; candidate reviews/day 12–120. Favorites may be saved even with zero monitoring; zero scouts pauses monitoring. Above 24 scouts the UI emphasizes heavy hardware demand and possible crashes. Forty is a configuration maximum, not a claim that all customer computers can handle it.
During beta, Starter and Creator have a 20 unique clip/day cap. Pro and Custom have no ClipBot posting cap. Cross-posts count once; failed uploads and retries do not consume extra allowance. All platform/account restrictions still apply.
Source: https://developers.tiktok.com/docs/en/content-sharing-guidelines

The proposed subscription formula is value/capacity pricing with inference headroom, not a claim that every scout/favorite has an API fee:
raw monthly price = 7 + 0.50*max(0,scouts-6) + 0.20*streamerFavorites + 0.20*categoryFavorites + 0.45*max(0,dailyReviews-12).
Final proposed price = max($10, raw rounded UP to the nearest $5).
Base includes up to 6 scouts, 12 reviews/day; reductions below included quantities do not reduce the base. $5 rounding means some small slider moves do not change the displayed price immediately. Each of the four sliders participates in the equation. Backend must recalculate against an approved versioned price book, never trust a submitted client dollar amount.

Maximum configuration: 40 scouts, 25 favorite streamers, 25 categories, 120 reviews/day.
Raw price $82.60 => proposed monthly subscription $85. This is a suggestion, not a purchased or active plan.
120 reviews/day x 31 days = 3,720 reviews. At the 20k input/2k output TOTAL per review Haiku example ($0.003), direct Claude tokens cost $11.16/month. Twice that token cost is $22.32; this stress case is not an absolute worst-case guarantee. A proposed atomic per-user Claude ceiling is ceil(2.2 * example cost), at least $2; maximum config gives $25/month. Stop dispatch at that ceiling and the workspace/global ceiling. This is not enforced yet.
For a $100 charge, a planning payment-fee example at 2.9%+$0.30 is $3.20 (check the chosen provider and country; billing-service fees/tax/refunds may add more). With a separate hypothetical $5 per-user operations contingency, the illustrative subtotal is $19.36 at example AI cost, $30.52 at the 2x token stress case, or $33.20 if the proposed $25 AI ceiling is fully used. These exclude any unallocated fixed hosting/database cost and are not a profitability or total-bill guarantee.
100 fully maxed users => $1,116 example Claude spend, up to $2,500 under only the individual caps. Owner-wide reservations and a hard global dispatch stop are still necessary to prevent the aggregate surprises the user is concerned about. A global cap must be coordinated with customer capacity commitments; don't sell more allowance than it can fund.

Customer view now shows subscription price and selected allowances, not internal raw API-cost estimates. Cloud media remains excluded. Platform publishing, billing, paid entitlement and real spend safeguards remain unimplemented.

Payment reference: https://stripe.com/pricing — standard US domestic cards: 2.9% + USD 0.30; USD 100 payment costs USD 3.20 before any separate billing or international fees.
Verification: 31 tests pass, including an exact USD 45 boundary regression. Currency calculation uses integer cents. Custom quote remains a local draft; server budget enforcement and billing are not active.

Beta update: posting is no longer a paid Custom slider. Maximum Custom proposal is $85/month, with unchanged AI allowance and spending protection. Starter and Creator allow 20 unique clips/day during beta; Pro and Custom have no ClipBot posting cap.
