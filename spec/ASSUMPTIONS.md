# Assumptions

Everything the datasets cannot supply, one rule per line, with why. Values live in
`adfill/sim/config.py`; a change there must change the line here.

## Viewing

| Rule | Value | Why |
|---|---|---|
| A MovieLens rating event is one viewing session of that title, starting at the rating timestamp | — | Ratings are the only timestamped title-level activity in the data. Nobody watched anything. |
| At most N sessions per viewer per day; the rest of that day's ratings are dropped | N = 3 | Users rate dozens of titles in one sitting on signup. That is not viewing. |
| Each viewer watches on one device class for the whole run | tv 55%, mobile 20%, desktop 15%, tablet 10% | The data has no device. Share leans TV, as ad-supported streaming does. |
| A title's genres are its MovieLens genres; "(no genres listed)" is empty | — | Real data. |

## Breaks

| Rule | Value | Why |
|---|---|---|
| Breaks per session | 1: 30%, 2: 35%, 3: 25%, 4: 10% | Sessions vary in length; the data has no durations. |
| First break at session start, then one every 15 minutes | 900 s | Pre-roll plus mid-rolls at a steady cadence. |
| Break length | 30 s: 20%, 60 s: 40%, 90 s: 25%, 120 s: 15% | Short pods dominate; two-minute pods exist. |
| Creative duration | 15 s or 30 s, equally likely | The two standard video spot lengths. |
| Ad load cap per viewer | 240 s in any trailing hour | A light ad load, typical of an ad-supported tier. Breaks are shortened to fit. |
| A break with no exact-fit pod is filled as fully as possible; the gap goes to house promos | tolerance 0 s | Exact fit first; an unfilled break is still a legal break. |

## Programmatic demand

| Rule | Value | Why |
|---|---|---|
| Bids per break | Poisson, mean 4 | The data has bids per impression, not per break. |
| Bid CPM shape | sampled from real Criteo per-impression `cost`, one Criteo campaign per programmatic advertiser | Real within- and between-advertiser spread: p90 is 8.6× the median, p99 45×. |
| Which Criteo campaigns | 60 drawn per seed from the 346 with 10,000+ impressions | Enough rows per campaign to sample its distribution. |
| Bid CPM level | pooled median of the chosen campaigns scaled to $18 | Criteo costs are in undisclosed scaled units; the level is a choice, the shape is data. |
| Criteo costs are treated as bids | — | They are clearing prices of won impressions (censored). Phase 3 models the censoring. |
| Criteo is display retargeting, not video | — | The only large public per-impression price set available. Stated as a limitation. |
| Device price multiplier | tv 1.3, mobile 0.8, desktop 0.9, tablet 0.9 | TV inventory clears higher. |
| Programmatic advertisers | 60, each in one fixed category | See the category rule below. |
| Bid price is what the buyer pays | — | Value-based allocation, pay-as-bid. Not a second-price auction. |
| Fallback price source (`lognormal`, tests only) | median $18, σ 0.7, per-advertiser σ 0.3 | Lets tests and fresh clones run without the download. |

## Guaranteed deals

| Rule | Value | Why |
|---|---|---|
| Campaigns | 40 | Enough overlap for deals to contend for the same breaks. |
| Contract CPM | uniform $30–50 | Guaranteed video sells above the open-market median. |
| Makegood owed per undelivered impression | 1.0 × contract CPM, on top of the forgone payment | A chosen parameter, not a market fact. Swept in results. |
| Flight length | uniform 14–45 days, clipped to the window | Typical flight lengths. |
| Genre targeting | 70% of deals target 1–3 of the 12 most common genres; the rest are untargeted | Mix of narrow and broad buys. |
| Device targeting | 40% of deals buy TV only | TV-only is the common premium restriction. |
| Deal size | weight ~ uniform(0.05, 0.7) × own forecast matching supply; the whole book is then scaled to 40% of forecast ad slots | Deals overlap; sizing each alone oversold the book 1.7× (BUG_LOG B1). |
| Deals are booked before the window opens and sized from pre-window history | — | That is when a sales team sizes them (BUG_LOG B4). |

## Structural

| Rule | Why |
|---|---|
| Each advertiser belongs to exactly one product category | Competitive separation is by category; the pod solver relies on it and rejects input that breaks it. |
| Guaranteed and programmatic advertisers are disjoint | Keeps one-advertiser-per-pod unambiguous. |
| A served ad is a delivered impression | Completion is modelled in Phase 2. |

## Performance demand (Phase 2, `price_source = "criteo-cpa"`)

| Rule | Value | Why |
|---|---|---|
| Programmatic buyers pay per conversion, not per impression | — | Makes the predicted rate load-bearing: the allocator ranks by CPA × predicted rate but is paid CPA × actual outcome. |
| Each bid is a real Criteo impression from the test days (24–30), with its real features and conversion label | sampled with replacement per advertiser | No model has trained on a row it is later valued on. |
| Advertiser CPA = its anchored CPM ÷ 1000 ÷ its average conversion rate | — | At its average rate, each advertiser is worth what it was worth in Phase 1; only per-impression valuation changes. |
| "Conversion" is the dataset's `conversion` label (a conversion within 30 days of the impression) | 4.84% on test days | Real label; several impressions can share one conversion. |
| The Criteo user and outcome are independent of the simulated video context (title, device) | — | The datasets do not link. Stated as a limitation. |
| Row sampling does not depend on the rate model | — | Every model is compared on identical impressions and outcomes. |
