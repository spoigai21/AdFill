"""Forecast validation on held-out periods (SPEC §6).

Replays each world's breaks in order. At the start of every day, each forecaster (primed on history,
observing arrivals only) predicts:
- each in-flight campaign's remaining matching supply, scored against what actually arrived, grouped by
  days left in the flight;
- total breaks and total programmatic spend over the next 1 and 3 days, scored against what arrived.
  (A 7-day horizon would be useless for comparison: seven day-of-week factors sum to 7 by construction.)
"Spend" is the cash the market offered: per break, the expected value of the highest bid.
"""

from __future__ import annotations

from bisect import bisect_left
from collections import defaultdict
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean, median

from adfill.core.eligibility import eligible
from adfill.core.model import SECONDS_PER_DAY
from adfill.forecast.seasonal import SeasonalForecast, dow
from adfill.sim.config import SimConfig
from adfill.sim.world import movielens_world

BUCKETS = ((1, 3), (4, 7), (8, 14), (15, 60))
HORIZONS = (1, 3)


def _bucket(days_left: float) -> str:
    for lo, hi in BUCKETS:
        if days_left <= hi:
            return f"{lo}-{hi}"
    return f"{BUCKETS[-1][0]}+"


def validate_world(world) -> dict:
    forecasts = {"naive": world.make_forecast("naive"), "seasonal": world.make_forecast("seasonal")}
    times = {c.id: [] for c in world.campaigns}
    for b in world.breaks:
        for c in world.campaigns:
            if eligible(c, b):
                times[c.id].append(b.t)
    day_breaks: dict[int, int] = defaultdict(int)
    day_spend: dict[int, float] = defaultdict(float)
    for b in world.breaks:
        d = b.t // SECONDS_PER_DAY
        day_breaks[d] += 1
        day_spend[d] += max((x.cpm for x in b.bids), default=0.0) / 1000
    hist_spend: dict[int, float] = defaultdict(float)
    for b in world.history:
        hist_spend[b.t // SECONDS_PER_DAY] += max((x.cpm for x in b.bids), default=0.0) / 1000

    first_day = world.window_start // SECONDS_PER_DAY
    last_day = first_day + world.window_days
    supply_err = {k: defaultdict(list) for k in forecasts}
    horizon_err = {k: {f"{h}d_{m}": [] for h in HORIZONS for m in ("breaks", "spend")} for k in forecasts}
    spend_by_day = dict(hist_spend)
    i = 0
    for day in range(first_day, last_day):
        now = day * SECONDS_PER_DAY
        while i < len(world.breaks) and world.breaks[i].t < now:
            for f in forecasts.values():
                f.observe(world.breaks[i])
            i += 1
        for c in world.campaigns:
            if not (c.start <= now < c.end):
                continue
            ts = times[c.id]
            real = len(ts) - bisect_left(ts, now)
            if real == 0:
                continue
            bucket = _bucket((c.end - now) / SECONDS_PER_DAY)
            for name, f in forecasts.items():
                supply_err[name][bucket].append(abs(f.matching_supply(c, now) - real) / real)
        trail = range(day - world.history_days, day)
        level_b = sum(sum(v.values()) for dd, v in forecasts["naive"]._days) / world.history_days
        level_s = sum(spend_by_day.get(d, 0.0) for d in trail) / world.history_days
        seasonal: SeasonalForecast = forecasts["seasonal"]
        seasonal._roll_to(day)
        factors = seasonal._factors()
        for h in HORIZONS:
            if day + h > last_day:
                continue
            real_b = sum(day_breaks[d] for d in range(day, day + h))
            real_s = sum(day_spend[d] for d in range(day, day + h))
            for name, mult in (("naive", float(h)), ("seasonal", sum(factors[dow(d)] for d in range(day, day + h)))):
                horizon_err[name][f"{h}d_breaks"].append(abs(level_b * mult - real_b) / real_b)
                horizon_err[name][f"{h}d_spend"].append(abs(level_s * mult - real_s) / real_s)
        spend_by_day[day] = day_spend[day]
    return {"supply": supply_err, "horizon": horizon_err}


def validate(ml_dir: Path, windows: list[str], seeds: list[int], days: int, history_days: int, cfg: SimConfig) -> dict:
    supply = {k: defaultdict(list) for k in ("naive", "seasonal")}
    horizon = {k: {f"{h}d_{m}": [] for h in HORIZONS for m in ("breaks", "spend")} for k in ("naive", "seasonal")}
    for w in windows:
        start = int(datetime.fromisoformat(w).replace(tzinfo=timezone.utc).timestamp())
        for s in seeds:
            world = movielens_world(ml_dir, replace(cfg, seed=s), start, days, history_days, 1.0)
            r = validate_world(world)
            for name in supply:
                for b, xs in r["supply"][name].items():
                    supply[name][b] += xs
                for k in horizon[name]:
                    horizon[name][k] += r["horizon"][name][k]
    order = [f"{lo}-{hi}" for lo, hi in BUCKETS]
    return {
        "windows": windows, "seeds": seeds,
        "remaining_supply_median_ape_by_days_left": {
            name: {b: {"median_ape": round(median(v[b]), 4), "n": len(v[b])} for b in order if v[b]}
            for name, v in supply.items()},
        "horizon_mape": {name: {k: round(mean(xs), 4) for k, xs in v.items()} for name, v in horizon.items()},
    }
