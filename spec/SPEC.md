# AdFill — a guaranteed-delivery ad decision engine for streaming video

A decision engine that fills ad breaks in streaming video when two incompatible kinds of demand want
the same slot: campaigns whose impressions were **sold months in advance**, and bids arriving **right
now**. It prices a promise so it can compete with cash, fills each break with a legal pod, and then
proves the result beat both of the obvious simple rules.

---

## 1. The problem

A streaming service sells the same inventory two ways.

**Guaranteed (sold ahead).** An advertiser commits in October to *10 million impressions on drama
titles during December*, at an agreed price per thousand. The service has promised those impressions.
Fail to deliver, and it owes a **makegood** — replacement inventory or money back.

**Programmatic (sold on the spot).** A bid arrives for one specific impression: *$12 for this
viewer, now.*

A viewer hits an ad break. Both want the slot. Only one can have it.

### Both simple rules lose money

| Rule | What it gets right | What it costs |
|---|---|---|
| **Guaranteed first** | every deal delivers | gives away slots someone would pay a premium for, to satisfy an obligation that could have been met later from inventory nobody wanted |
| **Highest bid wins** | maximum cash today | under-delivers signed deals, owes makegoods worth more than the extra revenue, and loses advertiser trust |

The correct choice changes **slot by slot**, and depends on how close each promise is to failing.
Computing that is the project.

### Why it is technically interesting

The decision has no stable answer. A guarantee's worth is not a property of the guarantee — it is a
function of time remaining, delivery progress, and how much *matching* supply is still coming. The
same campaign should lose a contested slot in week one and win it in week four, with no change to its
terms. The engine has to derive that price continuously, from a supply forecast that is itself
uncertain.

---

## 2. Core model

### 2.1 Put both kinds of demand on one scale

A bid is a number. An obligation is not. Convert the obligation by asking what it costs to skip it:

```
value(guaranteed campaign) = makegood_penalty_per_impression
                           x  urgency(campaign, now)

value(programmatic bid)    = bid

winner = argmax over all eligible candidates
```

### 2.2 Urgency — the one formula that matters

Two quantities, and neither is sufficient alone.

**Delivery debt.** What is still owed, and how long is left.

```
debt          = promised - delivered
days_left     = deal_end - now
required_rate = debt / days_left
```

**Matching supply.** How many *eligible* impressions are forecast for the rest of the flight — only
inventory that satisfies this campaign's targeting counts. A comedy impression does not pay down a
drama deal. Eligibility is semantic, not categorical — see §5.

```
required_win_share = debt / forecast_matching_supply(campaign, now .. deal_end)
```

`required_win_share` is the control variable:

| Value | Meaning | Behaviour |
|---|---|---|
| < 0.3 | ample slack | cheap to skip; cash bids should usually win |
| 0.5 – 0.8 | tightening | competitive with mid-range bids |
| > 0.9 | nearly every matching slot is needed | should beat almost any bid |
| > 1.0 | **cannot be delivered** | take every matching slot, and flag the oversell |

Urgency must be **flat while slack exists and steep as the share approaches 1**, not linear. A linear
ramp makes guarantees outbid cash far too early and leaves revenue on the table. The exact curve is a
tunable parameter, and §8 requires reporting sensitivity to it.

### 2.3 Predicted action rate — where the model sits

A raw bid is not what an impression is worth. Real systems score demand as

```
value = bid  x  predicted_action_rate   (+ a quality term)
```

because a $2 bid on an impression that converts 5% of the time beats a $10 bid that never converts.
This is where machine learning enters, and it is load-bearing rather than decorative:

- **For programmatic**, the predicted rate scales the bid — so allocation quality depends directly on
  the model.
- **For guaranteed**, it decides *which* eligible impressions to spend a promise on. Two impressions
  both satisfy a drama deal; the model says which one the advertiser would rather have. That is how a
  campaign hits its goal *and* performs.
- **For pods in video specifically**, a predicted **completion rate** per creative and pod position
  orders the pod — viewers abandon long breaks, and a later slot is worth less than an earlier one.

**Calibration matters more than ranking accuracy here, and the reason is structural.** The predicted
rate is multiplied into the value, so a model that ranks perfectly but is 30% too high inflates every
value, distorts the comparison against guaranteed skip-costs, and corrupts pacing — which then
over- or under-delivers. A well-ordered but miscalibrated probability is worse than useless in a system
that *multiplies* by it.

So the model is evaluated on **calibration ratio** (mean predicted ÷ mean observed), expected
calibration error, and log loss — with AUC reported last, if at all. Splits are **time-forward**, never
random.

### 2.4 Why targeting width matters, and falls out for free

Two campaigns, identical debt:

| | Campaign A | Campaign B |
|---|---|---|
| Owed | 5M | 5M |
| Targeting | US, TV devices, dramas | unrestricted |
| Matching supply left | 6M | 80M |
| `required_win_share` | **0.83** | **0.06** |

A is nearly out of road; B has all the time in the world. When they contest a slot, A wins — not
because it is worth more, but because it cannot replace the slot. Narrow targeting makes a promise
fragile, and this formulation captures that without a special case.

---

## 3. Pod construction

Winning the auction is not the answer — a break needs a **set** of ads, in an order.

Given a break length and a set of winning candidates, produce a pod satisfying:

1. **Exact fit** — creative durations sum to the break length (or within a stated tolerance).
2. **One advertiser per pod** — no advertiser appears twice in the same break.
3. **Competitive separation** — no two creatives from the same product category adjacent.
4. **Ad-load limit** — respect a cap on ad seconds per viewing hour, tracked per viewer.
5. **Value maximisation** — among legal pods, pick the highest total value.

Solve it exactly (dynamic programming over duration slots) and compare against a greedy fill. Report
how far greedy falls below optimal, and the cost of solving exactly.

---

## 4. Data

### 4.1 Programmatic demand — real prices

The programmatic side needs a realistic distribution of what an impression costs. Two sources, in
order of preference:

**Primary: Criteo Attribution Modeling for Bidding** — 30.9 days, **16,468,027 rows**, **435,810
distinct conversions**, **675 campaigns**, 6,142,256 distinct users, ~2.4 GB uncompressed. Carries a
per-impression **`cost`** column plus `click`, `conversion`, `conversion_timestamp`, `click_pos`,
`attribution`, and `time_since_last_click`. Fetchable without a login (`go.criteo.net`, or the
HuggingFace mirror; the README's own S3 link is dead). CC BY-NC-SA 4.0.

**The dataset's own README is wrong, by roughly 10x on conversions.** It claims 45K conversions and 700
campaigns; the figures above were measured by streaming the file on 2026-09-28. Use the measured ones,
and say they were measured.

**Its click rate is 36.1% and is not a CTR.** The file is heavily subsampled toward clicks. The `cost`
column and the timing columns are what this project needs; the class balance must never be presented as
a real click-through rate.

Tooling note: every `go.criteo.net` path returns **404 to HEAD and 200 to GET**, so a `curl -I` probe
will wrongly suggest the dataset is gone.

**Optional, only if it can be obtained: iPinYou RTB** — the only public set with true auction
internals (`bidprice`, `payprice`, `slotprice`): 64.7M bids, 15.3M impressions, 11,557 clicks.
**Acquisition is the blocker, not the licence.** The UCL mirror times out, `data.computational-
advertising.org` fails DNS, and the only live download found is a Baidu Pan link. Do not design a
phase that depends on it. If it does become available, it upgrades the price realism; nothing in the
spec requires it.

**Known limitation: observed prices are censored.** A cost is recorded only for impressions that were
*won*. A loss says only that the price exceeded the bid. Any win-rate curve fitted on won impressions
alone is biased, and §6 must handle this explicitly rather than ignoring it.

### 4.2 Viewing sessions — real people, real titles

A public movie-ratings dataset (25M ratings, 162K users, 62K titles, with genres and timestamps)
supplies real users watching real titles with realistic temporal patterns. Rating events become
viewing sessions; breaks are inserted into sessions.

### 4.3 Content semantics — also real, via the tag genome

The same distribution ships a **tag genome**: ~15.6M rows scoring **1,128 tags** against each title
with a relevance weight — tags such as *violent*, *dark*, *feel-good*, *family*, *disturbing*,
*inspirational*. This is the substrate for contextual targeting and brand safety (§5), and it matters
for honesty as much as for capability: **content semantics are real measured data here, not an
assumption.** Genre buckets are the crude version of something the genome expresses directly.

### 4.4 Synthesized — and enumerated

The datasets contain nothing about ad breaks, so these are generated by fixed, documented rules:

- break length and break positions within a session
- creative duration
- device class
- the mapping from rating events to viewing sessions
- guaranteed deal terms (impression goals, targeting, flight dates, penalties)

**Every rule goes in `ASSUMPTIONS.md`, one per line, with its justification.** Nobody watched
anything; the viewers are simulated. This must be stated in the README, not buried.

---

## 5. Contextual targeting and brand safety

Genre matching is not how premium video inventory is actually sold. An advertiser buys *"premium
automotive, family-safe, aspirational"*, and two thrillers can be opposite buys.

**Semantic eligibility.** Represent each title as a vector over the tag genome (§4.3), represent an
advertiser brief the same way, and score eligibility by similarity rather than genre membership.

**Brand safety, the half nobody models.** Some placements must be *refused*: an airline ad against a
plane-crash thriller, a fast-food ad against an eating-disorder documentary. Safety rules are tag
thresholds a title must not exceed, and they matter structurally because **refusals shrink the matching
supply in §2.2** — which raises `required_win_share`, which raises the price of every affected promise.
Safety is not a filter bolted on the side; it propagates into the allocation.

**Measure:** predicted action rate under semantic matching versus genre matching; the share of inventory
removed by safety rules and its effect on delivery; and whether the avails forecast becomes more
accurate when eligibility is semantic rather than categorical.

---

## 6. Forecasting

The allocator's price is only as good as the supply estimate under it, which makes the forecaster
load-bearing rather than decoration.

**Avails.** For a proposed deal (targeting + flight window), estimate deliverable impressions from
historical viewing patterns. Refuse to accept a deal that would oversell inventory already promised.

**Win-rate curve.** For programmatic, estimate the probability of winning at a given bid — handling
the censoring in §4.1 rather than ignoring it. State the method and its assumption.

**Validation.** Forecast on one period, measure against a held-out one. Report error on both spend and
impression counts.

**Required failure experiment.** Run the allocator with a deliberately wrong forecast (biased ±30%) and
report how much revenue and delivery is lost. A system whose behaviour under a bad forecast is unknown
is not characterised.

---

## 7. Architecture

Deliberately small. One process, one language, files for storage.

```
request  ->  eligibility   targeting, flight dates, brand safety
         ->  caps          per-viewer frequency and ad-load counters
         ->  price         urgency for each guaranteed candidate (needs the forecast)
         ->  compare       guaranteed skip-costs vs programmatic bids, one scale
         ->  pod           exact-fit DP under the §3 constraints
         ->  record        append the decision to a log file
```

Delivery accounting, reach, and billing are computed by a **second pass over the decision log**, not
on the request path.

### Non-goals — explicitly out of scope

No message broker, no stream-processing framework, no relational database, no GraphQL layer, no web
console, no metrics stack, no RPC framework, no container orchestration. None of them changes whether
the allocation result is correct or interesting, and each is days of plumbing.

Throughput benchmarking is also out of scope. A single-machine requests-per-second figure with the
load generator on the same machine is a weak claim that costs more to defend than it earns. Report
**per-decision cost** instead, and report it once.

---

## 8. Metrics and baselines

Every experiment runs the same input through three policies:

| Policy | Rule |
|---|---|
| **Guaranteed-first** | serve any eligible guaranteed campaign; sell only leftovers |
| **Highest-bid** | always take the largest programmatic bid |
| **AdFill** | the §2 unified comparison |

### The headline result is a pair, never one number

One number alone is gameable: highest-bid maximises revenue and breaks every promise; guaranteed-first
keeps every promise and forgoes revenue. Report both together:

1. **Total revenue**, including makegood liability incurred
2. **Share of guaranteed campaigns delivered in full**

The claim to establish: AdFill earns more than guaranteed-first *and* delivers more than
highest-bid. Beating each baseline on the axis it is bad at.

### Supporting metrics

- **Cost of a guarantee** — programmatic revenue forgone to meet obligations
- **Delivery distribution** — per-campaign delivery as a share of goal, not just a pass count
- **Overspend** — campaigns exceeding their goal (wasted inventory)
- **Reach and frequency** — unique viewers per campaign and the frequency histogram; 10M impressions
  to 200K people is a failed reach campaign even at 100% delivery
- **Pod quality** — DP total value versus the exact optimum, and versus greedy
- **Model quality** — calibration ratio, expected calibration error, log loss on a future period;
  and the revenue/delivery difference the model makes versus a constant-rate stand-in
- **Forecast error** — on held-out periods, spend and impressions
- **Contextual lift** — predicted action rate under semantic eligibility versus genre matching
- **Cost of safety** — inventory removed by brand-safety rules, and the delivery effect
- **Exploration cost** *(Phase 6)* — regret against an oracle, and delivery forgone while learning
- **Sensitivity** — how the headline pair moves with the urgency curve shape and the penalty parameter
- **Per-decision cost** — microseconds, with the stage breakdown

---

## 9. Phases

Each phase ends with something complete and reportable. Stopping after any phase leaves a coherent
project, not a torso.

### Phase 1 — the allocator *(the phase that carries the project)*

Guaranteed and programmatic demand, eligibility, urgency pricing, pod construction, delivery
accounting, and both baselines.

**Supply forecast in Phase 1.** Urgency needs `forecast_matching_supply` (§2.2) before Phase 3 builds
a real forecaster, so Phase 1 uses a deliberately naive stand-in: the trailing average of matching
impressions per day over the simulated history, projected over the days left in the flight. It sits
behind the same interface Phase 3 replaces, so the allocator does not change when the forecast does.

**Done when:** a full simulated flight period runs under all three policies and prints the headline
pair, and the pod solver is verified against brute force on small catalogues.

### Phase 2 — prediction, contextual targeting, and brand safety

A calibrated action-rate model feeding the value computation in §2.3, plus a completion-rate model for
pod ordering. Time-forward splits. Compare a hashed logistic-regression baseline against a gradient-
boosted model.

Then §5: tag-genome content vectors, semantic eligibility in place of genre buckets, and brand-safety
refusal rules feeding back into matching supply.

**Done when:** calibration ratio, expected calibration error and log loss are reported on a held-out
future period; the headline pair is re-measured with the model in place versus a constant-rate
stand-in, showing what the model is worth in revenue and delivery terms; and semantic eligibility is
compared against genre matching with the cost of brand-safety refusals quantified.

### Phase 3 — forecasting and avails

Supply forecasting, oversell refusal, the censored win-rate curve, held-out validation, and the
wrong-forecast experiment.

**Done when:** forecast error is reported on a held-out period and the revenue/delivery cost of a ±30%
biased forecast is quantified.

### Phase 4 — reach, frequency, and ad load

Per-viewer frequency caps, unique-reach tracking, frequency histograms, and reach-goal campaigns
alongside impression-goal ones. The ad-load limit already enforced in Phase 1 (§3) is re-verified here
under duplicate and out-of-order delivery reports.

**Done when:** reach and frequency are reported per campaign and cap violations are zero under
duplicate delivery reports.

### Phase 5 — the live-event spike

A national live break where the entire audience arrives within seconds, so a campaign's whole day of
inventory appears at once. Pacing and caps must hold when supply is not spread over time.

**Done when:** the spike scenario is characterised, including what breaks and at what arrival rate.

### Phase 6 — creative selection as a constrained bandit *(optional, and the deepest)*

A campaign has several creative variants whose true rates are unknown until shown, so the engine must
explore. **Exploration costs delivery** — impressions spent learning are impressions not spent
optimally on a campaign that owes its goal by a deadline. That constraint is what separates this from a
textbook bandit.

Then the question replay cannot answer: *how do you know a policy you never ran would have done
better?* **Off-policy evaluation**, on a dataset where it is exactly identified rather than assumed — a
public bandit dataset logging the **propensity score on every row** (26.7M rows, no login, CC BY 4.0),
so the estimator rests on recorded probabilities instead of an assumption.

**Done when:** cumulative regret is reported against an oracle that knew the best variant from the
start; the delivery cost of exploration is quantified; the crossover is identified where exploring stops
being worth it because the deadline is near; and an off-policy estimate is validated against the
dataset's logged propensities.

---

## 10. Correctness

- **Property tests** on the pod solver: for thousands of random catalogues, the DP result equals brute
  force, and every returned pod satisfies all §3 constraints.
- **Invariants** on delivery accounting: impressions billed equal impressions logged; no campaign
  exceeds its goal by more than one impression; counters never drift under duplicated reports.
- **Determinism**: a fixed seed reproduces a run exactly. Every reported figure names the file it came
  from and the seed that produced it.
- **Bug log**: every bug found, and which test or experiment found it.

---

## 11. Cost and footprint

The project is designed to run entirely on one laptop with **no paid services**.

| Item | Cost |
|---|---|
| Criteo Attribution dataset (~2.4 GB uncompressed) | free, no login |
| MovieLens 25M incl. tag genome (~1 GB) | free, no login |
| Open Bandit Dataset (~11.75 GB, Phase 6 only) | free, no login, CC BY 4.0 |
| Compute | local; gradient-boosted trees and logistic regression are CPU-only |
| Storage | ~10 GB including intermediates |
| Hosting, cloud, GPU, LLM APIs | **none required** |

No GPU is needed — nothing here is a deep model, and a boosted-tree baseline on tens of millions of
rows is minutes of CPU. If a deep variant is ever wanted, it is an optional comparison, not a
dependency.

**Explicit non-dependency: no LLM.** Generative models solve none of the problems in this spec, and an
LLM bolted onto an allocation engine would be decoration. The machine learning here is rate prediction
and supply forecasting, which is what ads systems actually run on.

---

## 12. Limitations — to be published, not discovered

State these in the README:

1. The viewers are **simulated**. No human watched anything.
2. Break structure, creative durations, device classes, and deal terms are **synthesized** by the
   documented rules in `ASSUMPTIONS.md`.
3. The makegood penalty is a **chosen parameter**, not a market fact. Sensitivity is reported because
   the headline result depends on it.
4. Programmatic prices are **censored** (§4.1); the win-rate curve rests on a stated assumption.
5. Timing figures are from a **single machine**, and are per-decision costs rather than throughput
   claims.
6. Real inventory is not interchangeable the way the model assumes: viewer behaviour responds to ad
   load, and that feedback is not modelled.

A result whose limits are stated up front is a result. One that has to be extracted under questioning
is a liability.

---

## 13. Layout

```
README.md        overview, headline results, limitations (§12)
spec/            SPEC.md, ASSUMPTIONS.md, BUG_LOG.md, NUMBERS.md
core/            decision path, no I/O: eligibility, caps, urgency, pod solvers
content/         tag-genome vectors, semantic eligibility, brand-safety rules
forecast/        avails and win-rate estimation
predict/         action-rate and completion-rate models, calibration reporting
sim/             dataset loaders, session generation, deal generation, policy runner
report/          second pass over the decision log: delivery, reach, billing, metrics
tests/           property tests, invariants, determinism
data/            raw and derived datasets — not committed; see README for fetch steps
```

`NUMBERS.md` carries one row per reported figure: the number, the file it came from, the seed, and the
one sentence explaining how it was measured. No figure appears in a README or a summary without a row
here.
