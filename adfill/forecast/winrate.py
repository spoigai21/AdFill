"""The win-rate curve, estimated from censored feedback (SPEC §4.1, §6).

P(win | bid) for a new ad is the distribution F of the threshold T it must beat: the least value at
which the pod solver would include it. A buyer that learns T only when it wins (as second-price
feedback gives) sees an exact T on wins and only "T > bid" on losses: right-censored data. Fitting F on
wins alone is biased toward cheap slots, because expensive slots are exactly the ones it loses. The
Kaplan-Meier estimator uses the losses too, and is unbiased when bids are independent of T.

The Criteo data cannot show this: it holds won impressions only, with no losses at all. The simulation
can, because it can compute T exactly for every sampled break.
"""

from __future__ import annotations

import numpy as np

from adfill.core.model import Candidate, Kind
from adfill.core.pod import solve_exact

LOW, HIGH = 1e-6, 1.0  # $ per impression: $0.001 to $1,000 CPM
PROBE_S = 15


def threshold(cands: list[Candidate], length: int, iters: int = 30) -> float:
    """Least value at which a new 15 s ad from a new advertiser enters the best pod (inf if never).

    Uses the best pod up to the break length (no exact-fit requirement), where inclusion is monotone in
    the probe's value, so bisection is exact to the tolerance.
    """
    if length < PROBE_S:
        return float("inf")

    def wins(v: float) -> bool:
        probe = Candidate(Kind.PROGRAMMATIC, "_probe", "_probe", "_probe", PROBE_S, v, v * 1000)
        pod = solve_exact(cands + [probe], length, tolerance=length)
        return any(c.ref == "_probe" for c in pod.items)

    if not wins(HIGH):
        return float("inf")
    if wins(LOW):
        return LOW
    lo, hi = np.log(LOW), np.log(HIGH)
    for _ in range(iters):
        mid = (lo + hi) / 2
        if wins(float(np.exp(mid))):
            hi = mid
        else:
            lo = mid
    return float(np.exp(hi))


def kaplan_meier_cdf(observed: np.ndarray, event: np.ndarray, grid: np.ndarray) -> np.ndarray:
    """F(x) = 1 - S(x) from right-censored data: `observed` = min(T, bid), `event` = T was seen."""
    order = np.argsort(observed, kind="stable")
    t, e = observed[order], event[order]
    at_risk = len(t)
    surv, times, values = 1.0, [], []
    i = 0
    while i < len(t):
        j = i
        while j < len(t) and t[j] == t[i]:
            j += 1
        d = int(e[i:j].sum())
        if d:
            surv *= 1 - d / at_risk
            times.append(t[i])
            values.append(surv)
        at_risk -= j - i
        i = j
    times_a, values_a = np.array(times), np.array(values)
    idx = np.searchsorted(times_a, grid, side="right") - 1
    s = np.where(idx >= 0, values_a[np.clip(idx, 0, None)] if len(values_a) else 1.0, 1.0)
    return 1 - s


def empirical_cdf(sample: np.ndarray, grid: np.ndarray) -> np.ndarray:
    s = np.sort(sample)
    return np.searchsorted(s, grid, side="right") / len(s) if len(s) else np.zeros_like(grid)


def evaluate(thresholds: np.ndarray, bids: np.ndarray, grid: np.ndarray) -> dict:
    """Compare winners-only and Kaplan-Meier estimates of the win-rate curve against the truth."""
    won = bids >= thresholds
    truth = empirical_cdf(thresholds, grid)
    naive = empirical_cdf(thresholds[won], grid)
    km = kaplan_meier_cdf(np.minimum(thresholds, bids), won, grid)

    def bid_for(curve: np.ndarray, target: float) -> float:
        k = int(np.searchsorted(curve, target))
        return float(grid[min(k, len(grid) - 1)])

    out = {"win_rate_observed": round(float(won.mean()), 4)}
    for name, curve in (("winners_only", naive), ("kaplan_meier", km)):
        target_bid = bid_for(curve, 0.5)
        out[name] = {
            "max_abs_error": round(float(np.max(np.abs(curve - truth))), 4),
            "mean_abs_error": round(float(np.mean(np.abs(curve - truth))), 4),
            "bid_for_50pct_cpm": round(1000 * target_bid, 2),
            "true_win_rate_at_that_bid": round(float(empirical_cdf(thresholds, np.array([target_bid]))[0]), 4),
        }
    out["true_bid_for_50pct_cpm"] = round(1000 * bid_for(truth, 0.5), 2)
    return out
