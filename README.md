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
```

Data, unpacked under `data/` (not committed):
- [MovieLens 25M](https://grouplens.org/datasets/movielens/25m/) at `data/ml-25m/`
- [Criteo Attribution Modeling for Bidding](http://go.criteo.net/criteo-research-attribution-dataset.zip)
  (CC BY-NC-SA 4.0), unzipped, at `data/criteo/criteo_attribution_dataset.tsv.gz`. The dataset's README undercounts it; measured:
  16,468,027 rows and 675 campaigns.

## Limitations

1. The viewers are **simulated**. Viewing sessions are derived from MovieLens rating events; nobody
   watched anything.
2. Break structure, creative durations, device classes, programmatic prices and deal terms are
   **synthesized** by the rules in [`spec/ASSUMPTIONS.md`](spec/ASSUMPTIONS.md).
3. The makegood penalty is a **chosen parameter**, not a market fact.
4. Programmatic prices are real Criteo **display** clearing prices, not video bids. Only won
   impressions have a cost, so the prices are censored, and their level is anchored to an assumed
   $18 median CPM. The shape is data; the level is a choice.
5. The supply forecast is a trailing average that ignores competing campaigns. The best urgency curve
   likely depends on forecast quality, so the sweep is repeated when the forecaster improves.
6. Criteo users and outcomes are **independent of the simulated video context**: the datasets do not
   link, so content cannot influence conversion here.
7. Brand-safety rules and semantic briefs are **chosen thresholds** over real genome scores.
8. Timing figures are **per-decision costs on one laptop** (57 µs, pure Python), not throughput
   claims.
