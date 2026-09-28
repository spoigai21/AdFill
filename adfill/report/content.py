"""Content measurements (SPEC §5) that the allocation sweep does not give directly.

- How much inventory brand safety refuses, per category, weighted by viewing.
- How much each campaign's matching supply shrinks when its category's rules apply.
- Whether the avails forecast is more accurate for semantic briefs than for genre targeting:
  forecast at booking time versus the matching breaks that actually arrived during the flight.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean, median

from adfill.content.index import content_index
from adfill.core.eligibility import eligible
from adfill.sim.config import SimConfig
from adfill.sim.sessions import load_titles
from adfill.sim.world import World, movielens_world


def _realized(world: World) -> dict[str, int]:
    out = {c.id: 0 for c in world.campaigns}
    for b in world.breaks:
        for c in world.campaigns:
            if eligible(c, b):
                out[c.id] += 1
    return out


def _forecast_errors(world: World) -> list[dict]:
    forecast = world.make_forecast()
    real = _realized(world)
    rows = []
    for c in world.campaigns:
        f = forecast.matching_supply(c, world.window_start)
        if real[c.id]:
            kind = "semantic" if c.targeting.brief else ("genre" if c.targeting.genres else "untargeted")
            rows.append({"campaign": c.id, "kind": kind, "forecast": round(f), "realized": real[c.id],
                         "ape": abs(f - real[c.id]) / real[c.id]})
    return rows


def measure(ml_dir: Path, windows: list[str], seeds: list[int], days: int, history_days: int) -> dict:
    titles = load_titles(ml_dir)
    content = content_index(ml_dir, frozenset(titles))
    refused_share: dict[str, list[float]] = {c: [] for c in content.unsafe}
    bid_refusal, shrink, errors = [], [], []
    for w in windows:
        start = int(datetime.fromisoformat(w).replace(tzinfo=timezone.utc).timestamp())
        for s in seeds:
            base = SimConfig(seed=s, price_source="lognormal")
            off = movielens_world(ml_dir, base, start, days, history_days, 1.0)
            n = len(off.breaks)
            for cat, bad in content.unsafe.items():
                refused_share[cat].append(sum(b.title in bad for b in off.breaks) / n)
            on = movielens_world(ml_dir, replace(base, brand_safety="after_booking"), start, days, history_days, 1.0)
            bid_refusal.append(on.stats["bids_refused"] / on.stats["bids_total"])
            r_off, r_on = _realized(off), _realized(on)
            shrink += [1 - r_on[c.id] / r_off[c.id] for c in off.campaigns if r_off[c.id]]
            for mode in ("genre", "semantic"):
                wd = off if mode == "genre" else movielens_world(
                    ml_dir, replace(base, targeting_mode="semantic"), start, days, history_days, 1.0)
                errors += [{**e, "window": w, "seed": s} for e in _forecast_errors(wd)]

    def ape(kind):
        xs = [e["ape"] for e in errors if e["kind"] == kind]
        return {"campaigns": len(xs), "median_ape": round(median(xs), 4), "mean_ape": round(mean(xs), 4)}

    return {
        "windows": windows, "seeds": seeds,
        "viewing_refused_by_category": {c: round(mean(v), 4) for c, v in refused_share.items()},
        "viewing_refused_mean": round(mean(mean(v) for v in refused_share.values()), 4),
        "programmatic_bids_refused": round(mean(bid_refusal), 4),
        "campaign_supply_shrink": {"mean": round(mean(shrink), 4), "median": round(median(shrink), 4),
                                   "max": round(max(shrink), 4)},
        "forecast_error": {k: ape(k) for k in ("genre", "semantic", "untargeted")},
    }
