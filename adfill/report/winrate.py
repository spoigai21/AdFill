"""Run AdFill over held-out worlds, sample breaks, compute each one's true threshold, and compare how
well a buyer could reconstruct the win-rate curve from censored feedback."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from adfill.core.caps import AdLoadTracker
from adfill.core.engine import Engine, Policy
from adfill.core.urgency import UrgencyCurve
from adfill.forecast.winrate import evaluate, threshold
from adfill.sim.config import SimConfig
from adfill.sim.world import movielens_world


def sample_thresholds(world, cfg: SimConfig, n: int, seed: int) -> np.ndarray:
    rng = np.random.default_rng([seed, 0x714])
    pick = set(rng.choice(len(world.breaks), min(n, len(world.breaks)), replace=False).tolist())
    ids = {world.breaks[i].id for i in pick}
    out: list[float] = []

    def hook(brk, length, cands):
        if brk.id in ids:
            out.append(threshold(list(cands), length))

    engine = Engine(Policy.ADFILL, world.campaigns, world.make_forecast(), UrgencyCurve(cfg.urgency_exponent),
                    AdLoadTracker(cfg.max_ad_seconds_per_hour), cfg.pod_tolerance_s, on_candidates=hook)
    for b in world.breaks:
        engine.decide(b)
    return np.array(out)


def run(ml_dir: Path, windows: list[str], seeds: list[int], per_world: int, bid_median_cpm: float,
        bid_sigma: float) -> dict:
    cfg = SimConfig(price_source="criteo-cpa", rate_model="gbm")
    thresholds = []
    for w in windows:
        start = int(datetime.fromisoformat(w).replace(tzinfo=timezone.utc).timestamp())
        for s in seeds:
            world = movielens_world(ml_dir, replace(cfg, seed=s), start, 30, 14, 1.0)
            thresholds.append(sample_thresholds(world, replace(cfg, seed=s), per_world, s))
    t = np.concatenate(thresholds)
    rng = np.random.default_rng(0xB1D)
    bids = bid_median_cpm / 1000 * np.exp(bid_sigma * rng.standard_normal(len(t)))  # independent of T
    grid = np.quantile(bids, np.linspace(0.05, 0.95, 91))
    return {
        "windows": windows, "seeds": seeds, "breaks_sampled": int(len(t)),
        "never_winnable_share": round(float(np.isinf(t).mean()), 4),
        "free_slot_share": round(float((t <= 1.01e-6).mean()), 4),
        "threshold_median_cpm": round(float(1000 * np.median(t[np.isfinite(t)])), 2),
        "buyer_bids": {"median_cpm": bid_median_cpm, "sigma": bid_sigma},
        **evaluate(t, bids, grid),
    }
