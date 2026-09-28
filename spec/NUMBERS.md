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
