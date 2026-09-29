# AdFill

A decision engine for ad breaks in streaming video, for the case where two incompatible kinds of demand
want the same slot: **guaranteed** campaigns whose impressions were sold months ahead, and
**programmatic** bids arriving right now. AdFill prices a promise by what it would cost to break it, so
it can compete with cash on one scale; fills each break with a legal pod (exact length, one ad per
advertiser, no competitors back to back); and measures the result against the two obvious simple rules.

The design is in [`spec/SPEC.md`](spec/SPEC.md).

## Phase 1 result

On held-out data, AdFill earned **38% more** than serving guaranteed campaigns first, while delivering
**239 of 240** guaranteed campaigns in full. Always taking the highest bid delivered **65 of 240**.

| Policy | Revenue vs guaranteed-first | Campaigns delivered in full |
|---|---|---|
| Guaranteed-first | — | 240 / 240 |
| Highest bid | +11.2% | 65 / 240 |
| **AdFill** | **+38.1%** (range +34.7% to +43.3%) | **239 / 240** |

Six simulated worlds: two 30-day MovieLens windows from 2018, three seeds each, about 34,000 ad breaks
per world, with programmatic prices sampled from real Criteo impression costs. Revenue counts makegoods
owed at 1× the contract CPM per undelivered impression. Every figure, with its source file, is in
[`spec/NUMBERS.md`](spec/NUMBERS.md).

**How the urgency curve was chosen.** A promise's urgency is `share ^ k`, where `share` is the fraction
of the remaining matching slots the campaign still needs. The intuitive design is flat-then-steep
(large `k`): let cash win early. It lost. With `k = 4`, AdFill delivered only 22 of 360 campaigns in
full, because every campaign waited and they collided near their deadlines. `k = 0.5` was the best on
2016–2017 tuning windows ([sweep](results/sweep-phase1-low.md)), was committed, and was then checked on
the 2018 windows above, which played no part in choosing it.

**Does it depend on the assumed price level?** Programmatic prices have a real shape but an assumed
level. Halving and doubling that level on the same held-out worlds:

| Median bid | AdFill revenue vs guaranteed-first | AdFill delivered in full | Highest bid delivered in full |
|---|---|---|---|
| $9 | +27.6% | 239 / 240 | 65 / 240 |
| $18 | +38.1% | 239 / 240 | 65 / 240 |
| $36 | +44.2% | 199 / 240 | 65 / 240 |

The claim holds at every level, but the delivery margin shrinks as cash gets richer relative to
guaranteed contract prices ($30–50): promises then need to start competing earlier, and `k = 0.25`
restores 236 / 240 at $36. The right curve depends on the ratio of open-market prices to contract
prices; it is not a universal constant.

**Pods.** The exact solver finds a pod that fills the break exactly 92.3% of the time; a greedy fill
manages 88.9%, gets 98.1% of the exact solver's total value, and is worse on 29% of breaks (by up to 50%
on one). The exact solver costs 51 µs per break against greedy's 6 µs, and is checked against brute
force on thousands of random catalogues. A full decision costs 57 µs, two-thirds of it in the pod
solver ([breakdown](results/pods-2018-03-01-s1.json)).

## Phase 2 result: prediction, content and brand safety

Programmatic buyers now pay **per conversion**. Each bid is a real Criteo impression from the last seven
days of the dataset, which no model trained on, carrying its real outcome. The allocator ranks a bid by
CPA × predicted conversion rate, but is paid CPA × what actually happened, so a bad model costs money.

**The model.** Trained on days 0–19, calibrated on 20–23, tested on 24–30 (3.47M impressions):

| Model | Calibration ratio | ECE | Log loss | AUC |
|---|---|---|---|---|
| Constant rate per campaign | 1.030 | 0.0020 | 0.1742 | 0.747 |
| Hashed logistic regression | 1.025 | 0.0013 | 0.1552 | 0.829 |
| Gradient-boosted trees | **1.007** | **0.0006** | **0.1519** | **0.840** |

**What the model is worth.** Replacing the constant rate with gradient-boosted trees earns **+7.8%**
revenue at the same delivery (240 / 240). Perfect foresight would earn a further 23.5%.

**Ranking earns the money; scale moves the trade-off.** Multiplying every prediction by the same factor
cannot reorder bids against each other, so the calibration step itself changed revenue by under 0.3%.
What scale does change is how cash compares with a promise:

| Median bid | Predictions | AdFill revenue | Delivered in full |
|---|---|---|---|
| $36 | calibrated | (baseline) | 232 / 240 |
| $36 | 30% too high | **+0.1%** | **208 / 240** |
| $36 | 30% too low | −1.4% | 239 / 240 |

Over-predicting looks free on revenue and quietly breaks 24 more promises. That is why the headline is a
pair: either number alone would have missed it.

**Brand safety.** Per-category rules over the MovieLens tag genome (gore, disaster, suicide, …) refuse
15–23% of viewing, 17% of programmatic bids, and on average 16% of each guaranteed campaign's matching
supply. With 40% of slots sold as guaranteed, that costs AdFill 9.9% of revenue and no delivery. Sell
60% and the same rules cut campaigns delivered in full from **231 to 180 of 240**: refusals shrink
supply, which raises what each promise needs, until the book no longer fits the inventory that is left.
Knowing the rules at booking time did not help (180 vs 179), because booking still sold 60% of *all*
slots. Refusing deals that exceed brand-safe avails is Phase 3's job.

**Semantic targeting.** Buying mood briefs ("feel-good family", "suspense") from the tag genome instead of
genres left the headline unchanged, and made the supply forecast *less* accurate: 8.4% median error
against 6.2% for genres, because briefs cut viewing into smaller, noisier slices.

**Not built, on purpose.** A completion-rate model for pod ordering, and a model of which impressions a
guaranteed advertiser would prefer: no public data carries either outcome, so both would learn only
what the simulation invented.

## Phase 3 result: forecasting, avails and win rates

**Forecasting.** A day-of-week forecaster halves short-horizon error on held-out data: next-day breaks
20.8% → 11.0%, next-day spend 21.9% → 11.9%, and a campaign's remaining supply in the **last three days of
its flight** 20.4% → 12.0%, exactly where urgency is decided. Over whole flights the two agree.

**The urgency curve, answered.** Phase 1 found the intuitive flat-then-steep curve lost, and blamed a
forecast that ignores competing campaigns. Adding a contention adjustment (each campaign expects only
its share of a break's slots when several want it) tested that:

| Forecast | Curve | Revenue vs guaranteed-first | Delivered in full |
|---|---|---|---|
| Naive | `k = 0.5` | +19.0% | 240 / 240 |
| Naive | `k = 2` | +6.6% | 72 / 240 (makegoods $1,033) |
| Contention-aware | `k = 2` | **+18.9%** | **240 / 240** |
| Contention-aware | `k = 4` | +21.1% | 234 / 240 (makegoods $0.32) |

Held-out 2018 worlds; `k = 2` was chosen on 2016–17 and committed before this run. With the better
forecast, the intuitive curve works and every `k` from 0.5 to 2 keeps every promise, so a wrong curve
choice degrades gently instead of falling off a cliff. It earns no more money; it is harder to break.

**Avails: refusing to oversell.** Each proposed deal is checked with a max-flow over forecast supply
(one ad per campaign per break, limited slots per break, brand-safe inventory only) and trimmed or
refused if it would oversell what is already sold. On the Phase 2 book that broke 60 promises:

| Booking | Share of ask booked | Revenue | Delivered in full | Makegoods |
|---|---|---|---|---|
| No check | 100% | $22,625 | 180 / 240 | $134 |
| Check, 10% margin | 76% | $20,654 | **161 / 162** | **$0** |
| Check, forecast 30% optimistic | 97% | $22,511 | 197 / 226 | $51 |

At a 1× makegood, overselling pays in the short run: missing by a few impressions is cheap, so refusing
deals costs 8.7% of revenue. The pair shows what that revenue buys: 60 broken promises. An optimistic
booking forecast slides straight back into them.

**Wrong forecasts.** Biasing the allocator's forecast ±30% barely moves a slack book (+0.4% / −0.9%
revenue, 239–240 / 240). On a tight one, an optimistic forecast behaves like an over-confident model:
revenue +0.7%, while campaigns delivered in full fall 231 → 219 and makegoods rise elevenfold.

**Win rates from censored data.** A buyer that learns the price to beat only when it wins, and fits
the win-rate curve to its wins alone, is off by up to 34 points: aiming to win half its auctions, it bids
$10.98 CPM and wins 25.6%. Kaplan–Meier, which also uses the losses, is off by under 1 point and
prescribes $17.59, the true answer. Exact thresholds come from the pod solver at 9,000 sampled breaks;
22% of breaks cannot be won at any price because of the ad-load cap.

## Phase 4 result: reach, frequency and ad load

Advertisers buy people, not impressions. Uncapped, 19.7% of AdFill's guaranteed impressions went to a
viewer who had already seen that campaign three times.

| AdFill, held-out | Revenue | Delivered in full | Reach | Average frequency |
|---|---|---|---|---|
| No cap | $22,249 | 240 / 240 | 116,688 | 2.19 |
| 3 per viewer per day | $22,236 | 240 / 240 | 118,196 | 2.16 |
| **1 per viewer per day** | **$22,123** | 237 / 240 | **159,858** | **1.59** |

A daily cap of one buys **37% more reach for 0.6% of revenue**. (A cap of three barely binds: few
viewers see more than a handful of breaks a day.) Uncapped, AdFill already reaches 23.5% more people
than guaranteed-first from the same 254,964 impressions, because it does not pour every early slot into
whichever deal is first in line.

**Reach deals.** With a quarter of deals buying unique viewers instead of impressions, and urgency priced
on the share of upcoming traffic from viewers not yet reached, AdFill delivered all 60 reach deals in
full; highest-bid delivered 51.

**Duplicated, out-of-order delivery reports.** Every served ad emits a beacon; 5% are duplicated and all
arrive up to an hour late, out of order. Reconciling by impression id and checking on serve time gave
exact counts for every campaign and **zero** frequency-cap and ad-load violations in every run. Counting
beacons as they arrive overbills by 5%, miscounts every campaign, and reports thousands of cap
violations that never happened.

## Phase 5 result: the live-event spike

A national live break: the whole audience hits one two-minute break within ten seconds, so a deal's
entire day of inventory appears at once. The engine is single-threaded, so the thing a real deployment
gets wrong has to be modelled: many servers deciding in parallel, each seeing delivery counters that are
up to a second stale.

| Audience (× a normal day) | Arrivals / s | Stale counters: overshoot | Deals over goal | Scheduled throttle: overshoot |
|---|---|---|---|---|
| 1× | 113 | 460 | 21 / 64 | 2 |
| 3× | 340 | 5,004 | 64 / 64 | 38 |
| 10× | 1,134 | 20,937 | 63 / 64 | 92 |
| 30× | 3,403 | 98,749 | 64 / 64 | 318 |
| 100× | 11,344 | **390,392** | 64 / 64 | **227** |

**What breaks, and when.** The rule "no deal exceeds its goal by more than one impression" breaks first,
already at normal-day arrival rates. Money breaks later: at 100×, one deal received 28× its entire goal,
390,000 impressions went out unbilled, and revenue fell 1.6%. Throttling on last second's arrivals barely
helps (338,343 overshoot at 100×) because the first second of a spike is gone before it reacts. A
throttle scheduled from the event's planned audience holds the goal with no revenue cost. Getting that
audience wrong is asymmetric: overestimating it by 30% is safe (19 overshoot), underestimating it by 30%
leaks 9,460.

## Phase 6 result: exploration that owes a deadline

**Off-policy evaluation, checked against the truth.** The Open Bandit Dataset logs a uniform-random
policy and a Thompson-sampling policy run side by side in one A/B test, with the true propensity of every
action. Estimating Thompson sampling's click rate from the random log alone:

| Estimator | Estimate | Error vs on-policy truth (0.674%) |
|---|---|---|
| Naive (random log's own rate) | 0.512% | 24.0% |
| Direct method (click model) | 0.631% | 6.4% |
| IPS | 0.666% | 1.2% |
| Self-normalised IPS | 0.678% | **0.5%** |
| Doubly robust | 0.682% | 1.2% |

The truth falls inside the 95% bootstrap interval of IPS, SNIPS and DR.

**Creative selection when the goal has a deadline.** A campaign runs five creatives, each a real OBD item
with its real click rate, and has sold a click goal it can only meet by finding a good one. Every
impression spent exploring is a click the goal may not get back.

| Flight (impressions) | Trust last flight, never explore | Best Thompson-sampling variant | Rotate evenly |
|---|---|---|---|
| 5,000 | **38.6%** goals met | 36.3% | 21.0% |
| 10,000 | **37.6%** | 35.6% | 14.0% |
| 20,000 | 35.3% | **39.0%** | 9.7% |
| 100,000 | 38.4% | **73.0%** | 3.3% |
| 500,000 | 39.2% | **99.0%** | 1.6% |

Below about 15,000 impressions, exploring stops being worth it **for the goal**, even though it still
wins on average clicks (17.2% vs 19.0% regret at 5,000). A goal is a threshold, not an average, and
trusting a decent prior is a gamble that pays often enough on a short flight. Committing to the best
creative for the last 30% of the flight helps short and medium flights; rotating creatives evenly, a
common default, is the worst choice at every length.

## Run it

```sh
uv sync
uv run pytest                                   # no data needed
uv run adfill run --name demo --source synthetic --price-source lognormal

# real data
uv run adfill prep-criteo                       # after downloading Criteo (below)
uv run adfill run --name ml --source movielens --start 2018-03-01
uv run adfill sweep --name holdout-2018 --windows 2018-03-01 2018-09-01 --exponents 0.25 0.5 1.0
uv run adfill pods --start 2018-03-01 --seed 1
uv run adfill train-models                      # Phase 2: ~2 min, writes data/criteo/scored_test.parquet
uv run adfill sweep --name p2-gbm-x1.0 --windows 2018-03-01 2018-09-01 --exponents 0.5 \
  --makegood-ratios 1.0 --price-source criteo-cpa --rate-model gbm
uv run adfill content                           # brand-safety refusal and forecast accuracy
uv run adfill forecast                          # Phase 3: forecast validation, held-out
uv run adfill winrate                           # win-rate curve from censored feedback
uv run adfill spike                             # Phase 5: live event, 1x to 100x a normal day
uv run adfill bandit                            # Phase 6: off-policy evaluation, creative bandit (needs OBD)
uv run adfill sweep --name p4-cap1 --windows 2018-03-01 2018-09-01 --exponents 0.5 --makegood-ratios 1.0 \
  --price-source criteo-cpa --rate-model gbm --freq-cap 1   # reach, frequency and beacon audit per row
uv run adfill sweep --name p3-holdout-contention --windows 2018-03-01 2018-09-01 --exponents 0.5 1.0 2.0 4.0 \
  --makegood-ratios 1.0 --price-source criteo-cpa --rate-model gbm --contention
uv run adfill sweep --name p3-avails-book60-safety --windows 2018-03-01 2018-09-01 --exponents 0.5 \
  --makegood-ratios 1.0 --price-source criteo-cpa --rate-model gbm --book-share 0.6 --brand-safety on --avails
```

Data, unpacked under `data/` (not committed):
- [MovieLens 25M](https://grouplens.org/datasets/movielens/25m/) at `data/ml-25m/`
- [Criteo Attribution Modeling for Bidding](http://go.criteo.net/criteo-research-attribution-dataset.zip)
  (CC BY-NC-SA 4.0), unzipped, at `data/criteo/criteo_attribution_dataset.tsv.gz`. The dataset's README undercounts it; measured:
  16,468,027 rows and 675 campaigns.
- [Open Bandit Dataset](https://research.zozo.com/data_release/open_bandit_dataset.zip) (CC BY 4.0) at
  `data/obd/open_bandit_dataset/`; Phase 6 uses only `random/men` and `bts/men`.

## Limitations

1. The viewers are **simulated**. Viewing sessions are derived from MovieLens rating events; nobody
   watched anything.
2. Break structure, creative durations, device classes, programmatic prices and deal terms are
   **synthesized** by the rules in [`spec/ASSUMPTIONS.md`](spec/ASSUMPTIONS.md).
3. The makegood penalty is a **chosen parameter**, not a market fact.
4. Programmatic prices are real Criteo **display** clearing prices, not video bids. Only won
   impressions have a cost, so the prices are censored, and their level is anchored to an assumed
   $18 median CPM. The shape is data; the level is a choice.
5. The contention adjustment is a simple shared-slot model: it ignores programmatic competition and
   campaigns that finish early. Demand refused at booking is simply lost; in reality it may be sold
   later or elsewhere.
6. Criteo users and outcomes are **independent of the simulated video context**: the datasets do not
   link, so content cannot influence conversion here.
7. Brand-safety rules and semantic briefs are **chosen thresholds** over real genome scores.
8. Phase 5 models parallel serving as counters synced every second; it is a model of staleness, not a
   distributed system.
9. Phase 6's creatives are Open Bandit **fashion recommendations**, not video ads: the click rates and
   their spread are real, the setting is borrowed.
10. Timing figures are **per-decision costs on one laptop** (57 µs, pure Python), not throughput
   claims.
