# AdFill

A decision engine for ad breaks in streaming video, for the case where two incompatible kinds of demand
want the same slot: **guaranteed** campaigns whose impressions were sold months ahead, and
**programmatic** bids arriving right now. AdFill prices a promise by what it would cost to break it, so
it can compete with cash on one scale; fills each break with a legal pod (exact length, one ad per
advertiser, no competitors back to back); and measures the result against the two obvious simple rules.

## Result

| Policy | Revenue vs guaranteed-first | Guaranteed campaigns delivered in full |
|---|---|---|
| Serve guaranteed campaigns first | — | 240 / 240 |
| Always take the highest bid | +11.2% | 65 / 240 |
| **AdFill** | **+38.1%** (range +34.7% to +43.3%) | **239 / 240** |

Held-out: six simulated worlds (two 30-day MovieLens windows from 2018 × three seeds, ~34,000 ad breaks
each), programmatic prices sampled from real Criteo impression costs, makegoods charged on every
undelivered impression. The design is in [`spec/SPEC.md`](spec/SPEC.md); the full write-up is in
[`results/`](results/README.md).

## What it found

**Optimism looks free on revenue and quietly breaks promises.** That is why every result is reported as
a pair — revenue, and campaigns delivered in full — and it showed up in every phase:

- A conversion model over-predicting by 30%: revenue **+0.1%**, **24 more** broken promises.
  ([Phase 2](results/README.md#phase-2-prediction-content-and-brand-safety))
- A supply forecast 30% too optimistic: revenue **+0.7%**, **12 more** broken promises.
  ([Phase 3](results/README.md#phase-3-forecasting-avails-and-win-rates))
- Selling deals the inventory cannot carry: **+9.5%** revenue, **60** broken promises. A max-flow
  avails check refuses them. ([Phase 3](results/README.md#phase-3-forecasting-avails-and-win-rates))
- Delivery counters one second stale during a live event: the goal cap breaks at *normal* traffic; at
  100× a normal day, one deal goes 28× over its goal. ([Phase 5](results/README.md#phase-5-the-live-event-spike))
- Judging exploration by average clicks: it wins on average and still loses on *meeting the goal* for
  flights of 10,000 impressions or fewer. ([Phase 6](results/README.md#phase-6-exploration-that-owes-a-deadline))

Also measured:
- The intuitive "let cash win early, then fight" urgency curve **lost** in Phase 1 (22 of 360 campaigns
  delivered), and became the best choice once the forecast accounted for competing campaigns (Phase 3).
- A gradient-boosted conversion model earns **+7.8%** over a constant rate. Its ranking earns the money;
  its calibration decides where on the revenue-versus-promises trade-off the engine lands.
- A 1-per-day frequency cap buys **37% more reach for 0.6% of revenue**.
- Off-policy estimates land within **0.5–1.2%** of the true value on the Open Bandit Dataset, where the
  naive estimate is 24% off.

## How the claims are kept honest

- **Chosen before tested.** Every tuned choice was made on 2016–17 windows and committed before the 2018
  held-out run (commits `f68ddea` and `fb56051`).
- **Every number has a source.** [`spec/NUMBERS.md`](spec/NUMBERS.md) gives each figure's file, seeds and
  method. Every synthesized rule is in [`spec/ASSUMPTIONS.md`](spec/ASSUMPTIONS.md); every bug, and what
  caught it, in [`spec/BUG_LOG.md`](spec/BUG_LOG.md).
- **Reproducible.** Fixed seeds; the published results regenerate from a fresh clone and the raw
  downloads ([how](results/README.md#reproduce)).
- **Tested.** The pod solver matches brute force on thousands of random catalogues; invariants cover
  billing, caps, ad load and determinism (`uv run pytest`, no data needed).

## Run it

```sh
uv sync
uv run pytest                                                   # no data needed
uv run adfill run --name demo --source synthetic --price-source lognormal
```

The real-data runs need MovieLens 25M, the Criteo attribution dataset and the Open Bandit Dataset;
download links and the full command sequence are in [`results/README.md`](results/README.md#reproduce).

```
adfill/core/      the decision path: eligibility, caps, urgency, pod solver, engine (no I/O)
adfill/forecast/  supply forecasts, avails check, win-rate estimation
adfill/predict/   conversion-rate models and calibration metrics
adfill/content/   tag-genome briefs and brand-safety rules
adfill/bandit/    off-policy evaluation and the creative bandit
adfill/sim/       datasets, sessions, breaks, deals, live events, runner
adfill/report/    second passes over decision logs: delivery, reach, beacons, spike
spec/             design, assumptions, bug log, numbers ledger
results/          every published result, and the write-up
```

## Limitations

1. The viewers are **simulated** from MovieLens rating events; nobody watched anything.
2. Breaks, creative lengths, devices and deal terms are **synthesized** ([rules](spec/ASSUMPTIONS.md)).
3. The makegood penalty and the $18 median bid level are **chosen**; results are swept across both.
4. Prices are Criteo **display** clearing prices (won impressions only), not video bids.
5. Criteo buyers are **independent of the video context**: the datasets do not link.
6. The contention model ignores programmatic competition; demand refused at booking is simply lost.
7. Brand-safety rules and semantic briefs are **chosen thresholds** over real genome scores.
8. Parallel serving is modelled as counters synced every second, not as a distributed system.
9. Phase 6 creatives are Open Bandit **fashion recommendations**; the click rates are real, the setting
   is borrowed.
10. Timings are **per-decision costs on one laptop** (57 µs, pure Python), not throughput claims.
