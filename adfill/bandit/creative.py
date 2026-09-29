"""Creative selection as a bandit that owes a goal by a deadline (SPEC Phase 6).

A campaign runs K creatives. It has N impressions over its flight and sold G clicks, where
G = GOAL_SHARE x N x (best creative's rate): meetable only by finding and using a good creative. Every
impression spent on a weak creative is a click the goal may not get back, so exploration costs delivery.

Creatives are Open Bandit items with their real click rates. Truth comes from days 2-7 of the uniform
random log (unbiased); a "last flight" prior comes from day 1 only (about 2,300 impressions per item, so
it is noisy). The two never overlap.

Policies (posteriors updated in batches, as a serving system would):
- oracle: always the truly best creative (regret reference);
- uniform: rotate evenly (a common default);
- greedy_prior: trust last flight, never explore;
- ts: Thompson sampling from a flat prior;
- ts_prior: Thompson sampling started from last flight's counts;
- ts_deadline: ts_prior, but once the remaining impressions can no longer repay learning (the last
  COMMIT_SHARE of the flight) it commits to the posterior-best creative.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from adfill.bandit.ope import load

K = 5
GOAL_SHARE = 0.9
BATCH = 1_000
COMMIT_SHARE = 0.3
POLICIES = ("oracle", "uniform", "greedy_prior", "ts", "ts_prior", "ts_deadline")


def item_rates(campaign: str = "men") -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Per item: true rate (days 2-7), prior clicks and impressions (day 1)."""
    r = load("random", campaign)
    day = r.hour.dt.floor("D")
    first = day == day.min()
    truth = r[~first].groupby("item_id").click.mean()
    prior = r[first].groupby("item_id").click.agg(["sum", "count"])
    idx = truth.index.union(prior.index)
    return (truth.reindex(idx).to_numpy(), prior["sum"].reindex(idx).to_numpy(float),
            prior["count"].reindex(idx).to_numpy(float))


def simulate(truth, prior_clicks, prior_n, n_impressions: int, reps: int, seed: int) -> dict[str, dict]:
    rng = np.random.default_rng(seed)
    sets = np.array([rng.choice(len(truth), K, replace=False) for _ in range(reps)])  # (reps, K)
    p = truth[sets]
    best = p.max(axis=1)
    goal = np.floor(GOAL_SHARE * n_impressions * best)
    pc, pn = prior_clicks[sets], prior_n[sets]
    out = {}
    for policy in POLICIES:
        a = np.ones((reps, K)) + (pc if policy in ("ts_prior", "ts_deadline") else 0)
        b = np.ones((reps, K)) + ((pn - pc) if policy in ("ts_prior", "ts_deadline") else 0)
        clicks = np.zeros(reps)
        served = 0
        while served < n_impressions:
            m = min(BATCH, n_impressions - served)
            if policy == "oracle":
                counts = np.zeros((reps, K))
                counts[np.arange(reps), p.argmax(axis=1)] = m
            elif policy == "uniform":
                counts = np.full((reps, K), m / K)
            elif policy == "greedy_prior" or (policy == "ts_deadline" and served >= (1 - COMMIT_SHARE) * n_impressions):
                est = (pc + 1) / (pn + 2) if policy == "greedy_prior" else a / (a + b)
                counts = np.zeros((reps, K))
                counts[np.arange(reps), est.argmax(axis=1)] = m
            else:  # Thompson: one posterior draw per impression, shown creative = argmax
                draws = rng.beta(a[:, :, None], b[:, :, None], size=(reps, K, m))
                pick = draws.argmax(axis=1)
                counts = np.stack([(pick == k).sum(axis=1) for k in range(K)], axis=1).astype(float)
            got = rng.binomial(counts.astype(np.int64), p)
            a += got
            b += counts - got
            clicks += got.sum(axis=1)
            served += m
        out[policy] = {"clicks": clicks, "goal": goal}
    oracle = out["oracle"]["clicks"]
    return {pol: {
        "mean_clicks": round(float(v["clicks"].mean()), 2),
        "regret_vs_oracle": round(float((oracle - v["clicks"]).mean()), 2),
        "regret_share": round(float(((oracle - v["clicks"]) / np.maximum(oracle, 1)).mean()), 4),
        "goal_met_share": round(float((v["clicks"] >= v["goal"]).mean()), 4),
        "shortfall_share_of_goal": round(float((np.maximum(0, v["goal"] - v["clicks"]) / v["goal"]).mean()), 4),
    } for pol, v in out.items()}


def run(flights: list[int], reps: int, seed: int, campaign: str = "men") -> dict:
    truth, pc, pn = item_rates(campaign)
    return {
        "items": int(len(truth)), "k": K, "goal_share_of_best": GOAL_SHARE, "batch": BATCH,
        "commit_share": COMMIT_SHARE, "reps": reps,
        "true_rate": {"min": round(float(truth.min()), 5), "median": round(float(np.median(truth)), 5),
                      "max": round(float(truth.max()), 5)},
        "prior_impressions_per_item": int(np.median(pn)),
        "by_flight_impressions": {str(n): simulate(truth, pc, pn, n, reps, seed) for n in flights},
    }
