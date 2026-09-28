# Numbers

One row per figure that appears in the README or any summary: the number, the file it came from, the
seed, and how it was measured. A figure without a row does not get published.

| Figure | Value | Source file | Seed | How measured |
|---|---|---|---|---|
| Revenue lift, AdFill vs guaranteed-first, held-out | +38.1% mean (range +34.7% to +43.3%) | `results/holdout-2018.json` | 1, 2, 3 | Total revenue (programmatic + guaranteed billed − makegoods), per world, AdFill k=0.5 over guaranteed-first; mean/min/max over 6 worlds (2018-03 and 2018-09 × 3 seeds), makegood 1× CPM. |
| Campaigns delivered in full, held-out | AdFill 239/240; guaranteed-first 240/240; highest-bid 65/240 | `results/holdout-2018.json` | 1, 2, 3 | Campaigns with delivered ≥ goal, summed over the same 6 worlds. |
| Revenue lift, AdFill vs highest-bid, held-out | +24.2% mean | `results/holdout-2018.json` | 1, 2, 3 | As the first row, over highest-bid. |
| Makegood liability, held-out | AdFill $0.08; highest-bid $5,071.46 | `results/holdout-2018.json` | 1, 2, 3 | Undelivered impressions × makegood CPM, summed over the 6 worlds. |
| Revenue lift, AdFill vs guaranteed-first, tuning windows | +45.5% mean (range +41.1% to +50.9%) | `results/sweep-phase1-low.json` | 1, 2, 3 | As the first row, over 2016-03, 2016-09, 2017-03 × 3 seeds. The exponent was chosen here. |
| Campaigns delivered in full, tuning windows | AdFill 357/360; highest-bid 86/360 | `results/sweep-phase1-low.json` | 1, 2, 3 | As the second row, over the tuning worlds. |
| Breaks per world | ~34,000 | `results/holdout-2018.json` | 1, 2, 3 | Mean `breaks` over the held-out worlds (30-day windows, all MovieLens viewers). |
| Per-decision cost | 73.5 µs mean | `results/holdout-2018.json` | 1, 2, 3 | Mean wall time of `Engine.decide` for AdFill k=0.5, makegood 1×, one Apple M5 laptop, single process, pure Python. |
| Criteo rows / campaigns | 16,468,027 / 675 | `data/criteo/criteo_attribution_dataset.tsv.gz` | – | Counted by reading the full file on 2026-09-28. |
| Revenue lift, highest-bid vs guaranteed-first, held-out | +11.2% mean | `results/holdout-2018.json` | 1, 2, 3 | As the first row, highest-bid over guaranteed-first. |
| Campaigns delivered in full, AdFill k=4, tuning windows | 22/360 | `results/sweep-phase1.json` | 1, 2, 3 | Makegood 1×, summed over the 9 tuning worlds. |
| Greedy pod value as share of exact | 98.1% | `results/pods-2018-03-01-s1.json` | 1 | Sum of greedy pod values over sum of exact pod values (both limited to the break length), same candidate sets, 29,095 breaks of one held-out world. |
| Breaks where greedy is worse than exact | 29.4%; worst single break 49.6% below exact | `results/pods-2018-03-01-s1.json` | 1 | Share of compared breaks with greedy value below exact; largest relative gap on one break. |
| Exact-fit rate, exact vs greedy | 92.3% vs 88.9% | `results/pods-2018-03-01-s1.json` | 1 | Share of breaks filled to exactly their length. |
| Pod solve cost, exact vs greedy | 50.8 µs vs 6.0 µs per break | `results/pods-2018-03-01-s1.json` | 1 | Mean wall time per break, same laptop as the per-decision cost row. |
| Per-decision cost by stage | forecast+caps 1.3, eligibility+pricing 16.9, pod 38.7, record 0.4 µs; total 57.3 µs | `results/pods-2018-03-01-s1.json` | 1 | Mean per break from a run with no instrumentation hook. Lower than the 73.5 µs sweep figure, which ran 4 worlds in parallel on one machine. |
| Bid-level robustness, $9 median | +27.6% revenue vs guaranteed-first; 239/240 in full | `results/holdout-2018-bid9.json` | 1, 2, 3 | Held-out worlds, k=0.5, makegood 1×, bid median halved. |
| Bid-level robustness, $36 median | +44.2% revenue vs guaranteed-first; 199/240 in full (k=0.25: 236/240) | `results/holdout-2018-bid36.json` | 1, 2, 3 | Held-out worlds, k=0.5, makegood 1×, bid median doubled. |
| Conversion model, test days: calibration ratio / ECE / log loss / AUC | GBM 1.007 / 0.00058 / 0.1519 / 0.840; logistic 1.025 / 0.00127 / 0.1552 / 0.829; constant 1.030 / 0.00204 / 0.1742 / 0.747 | `results/predict-metrics.json` | 1 | Isotonic-calibrated on days 20–23, scored on all 3,465,012 rows of days 24–30; trained on 4M rows sampled from days 0–19. |
| Raw logistic calibration ratio | 1.118 | `results/predict-metrics.json` | 1 | As above, before isotonic calibration. |
| Revenue from the model, GBM vs constant rate | +7.75% (logistic: +6.86%) | `results/p2-gbm-x1.0.json`, `results/p2-constant-x1.0.json`, `results/p2-logistic_hashed-x1.0.json` | 1, 2, 3 | AdFill total revenue summed over the 6 held-out worlds, performance demand, k=0.5, makegood 1×. Delivery 240/240 (GBM) and 239/240 (constant). |
| Revenue left on the table vs perfect foresight | oracle +23.53% over GBM | `results/p2-oracle-x1.0.json` | 1, 2, 3 | As above with the true outcome as the rate. |
| Calibration step's revenue effect | raw vs calibrated logistic +0.28%; raw vs calibrated GBM −0.26% | `results/p2-logistic_hashed_raw-x1.0.json`, `results/p2-gbm_raw-x1.0.json` | 1, 2, 3 | As above. Within run-to-run noise. |
| AdFill vs baselines, performance demand | +19.08% revenue vs guaranteed-first; 240/240 vs highest-bid 67/240 | `results/p2-gbm-x1.0.json` | 1, 2, 3 | Held-out worlds, GBM rates. |
| Uniform ±30% miscalibration, $18 median | +30%: revenue +0.81%, 239/240; −30%: −1.85%, 240/240 | `results/p2-gbm-x1.3.json`, `results/p2-gbm-x0.7.json` | 1, 2, 3 | GBM rates multiplied by 1.3 or 0.7. |
| Uniform ±30% miscalibration, $36 median | +30%: revenue +0.12%, 208/240 in full, makegoods $25.29 (vs 232/240, $1.37); −30%: −1.39%, 239/240 | `results/p2-bid36-gbm-x*.json` | 1, 2, 3 | As above at doubled bid level. |
| Viewing refused by brand safety | 15.1% (retail, tech) to 22.7% (pharma); mean 17.0% | `results/content-2018.json` | 1, 2, 3 | Share of window breaks on titles refused for each category, including titles with no genome scores (refused as unverifiable). |
| Programmatic bids refused | 16.8% | `results/content-2018.json` | 1, 2, 3 | Refused bids over generated bids, window period. |
| Guaranteed matching supply removed by safety | mean 15.9%, max 30.4% per campaign | `results/content-2018.json` | 1, 2, 3 | 1 − eligible breaks with rules ÷ without, per campaign. |
| Cost of brand safety, 40% book | AdFill revenue −9.89%, delivery 239/240; highest-bid revenue −21.73% | `results/p2c-genre-off.json`, `results/p2c-genre-on.json` | 1, 2, 3 | Safety on vs off, held-out worlds, GBM rates. |
| Cost of brand safety, 60% book | AdFill delivered in full 231 → 180 of 240; makegoods $1.34 → $133.75 | `results/p2c-book60-off.json`, `results/p2c-book60-on.json` | 1, 2, 3 | Guaranteed book share raised to 60%. Rules known at booking: 180/240; after booking: 179/240. |
| Forecast error, genre vs semantic targeting | median APE 6.19% vs 8.41% (untargeted 5.20%) | `results/content-2018.json` | 1, 2, 3 | Forecast at window start vs eligible breaks realised during each flight; 164 campaigns per kind. |
| Semantic vs genre worlds, AdFill revenue | −1.05%; delivery 240/240 both | `results/p2c-semantic-off.json`, `results/p2c-genre-off.json` | 1, 2, 3 | Same book, briefs in place of genres. |
| Ratings on titles with genome scores | 95.7% | computed from `data/ml-25m` | – | Share of ratings from 2018-03-01 to 2018-10-01 whose title has genome scores, before the per-viewer-day session cap. |
