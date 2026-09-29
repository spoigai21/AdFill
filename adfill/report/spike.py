"""Characterise the live-event spike: what breaks, and at what arrival rate.

For each world and audience size, AdFill runs with instant counters (the ideal), with counters synced
every second (what parallel servers see), and with each throttle. Overshoot is impressions served past a
deal's goal: unbillable, and taken from cash buyers who would have paid.
"""

from __future__ import annotations

from concurrent.futures import ProcessPoolExecutor
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

from adfill.core.caps import AdLoadTracker
from adfill.core.eligibility import eligible
from adfill.core.engine import Engine, Policy
from adfill.core.urgency import UrgencyCurve
from adfill.report.delivery import headline
from adfill.sim.config import SimConfig
from adfill.sim.live import LIVE_GENRES, LIVE_TITLE, inject_live_event
from adfill.sim.runner import decision_row
from adfill.sim.world import movielens_world

VARIANTS = (  # (name, sync_s, throttle, audience forecast error)
    ("instant", 0, "none", None),
    ("sync1s", 1, "none", None),
    ("sync1s_reactive", 1, "reactive", None),
    ("sync1s_scheduled", 1, "scheduled", 1.0),
    ("sync1s_scheduled_under30", 1, "scheduled", 0.7),
    ("sync1s_scheduled_over30", 1, "scheduled", 1.3),
)


def _run(world, cfg, variant, event, log_path: Path):
    name, sync_s, throttle, audience_err = variant
    matching: dict[str, float] = {}

    def expected(c, t):
        """Known event: planned audience x the share of it this deal matches, spread over the window."""
        if not (event["start"] <= t < event["start"] + event["window_s"]):
            return 0.0
        if c.id not in matching:
            from adfill.core.eligibility import matches_targeting

            matching[c.id] = float(matches_targeting(c.targeting, LIVE_GENRES, "tv", LIVE_TITLE))
        return audience_err * event["breaks"] / event["window_s"] * sync_s * matching[c.id]

    engine = Engine(Policy.ADFILL, world.campaigns, world.make_forecast(), UrgencyCurve(cfg.urgency_exponent),
                    AdLoadTracker(cfg.max_ad_seconds_per_hour), cfg.pod_tolerance_s,
                    new_viewer_prior=world.stats.get("viewers_per_break", 0.5), sync_s=sync_s,
                    throttle=throttle, expected_arrivals=expected if audience_err else None, seed=cfg.seed)
    import json

    with log_path.open("w") as f:
        for b in world.breaks:
            f.write(json.dumps(decision_row(engine.decide(b)), separators=(",", ":")) + "\n")
    h, delivered = headline(log_path, world.campaigns)
    over = {c.id: max(0, delivered[c.id] - c.goal) for c in world.campaigns}
    live_matching = [c for c in world.campaigns if any(eligible(c, b) for b in world.breaks
                                                      if b.title == LIVE_TITLE and b.device == "tv")]
    return {
        "variant": name, "total_revenue": h.total_revenue, "delivered_in_full": h.delivered_in_full,
        "campaigns": h.campaigns, "makegood_liability": h.makegood_liability,
        "overshoot_impressions": sum(over.values()),
        "campaigns_over_goal_by_more_than_one": sum(v > 1 for v in over.values()),
        "worst_overshoot_share_of_goal": round(max((over[c.id] / c.goal for c in world.campaigns), default=0), 4),
        "deals_matching_event": len(live_matching),
    }


def run_world(task: dict) -> list[dict]:
    cfg = replace(SimConfig(seed=task["seed"]), **task["config"])
    start = int(datetime.fromisoformat(task["window"]).replace(tzinfo=timezone.utc).timestamp())
    base = movielens_world(Path(task["ml_dir"]), cfg, start, 30, 14, 1.0)
    out_dir = Path(task["run_dir"]) / f"{task['window']}-s{task['seed']}"
    out_dir.mkdir(parents=True, exist_ok=True)
    rows = []
    for m in task["multiples"]:
        world, event = inject_live_event(base, cfg, m)
        for v in VARIANTS:
            r = _run(world, cfg, v, event, out_dir / f"x{m}-{v[0]}.jsonl")
            rows.append({"window": task["window"], "seed": task["seed"], "multiple": m, **event, **r})
    return rows


def run(name: str, windows, seeds, multiples, ml_dir: str, run_dir: str, workers: int, config: dict) -> list[dict]:
    tasks = [{"window": w, "seed": s, "multiples": multiples, "ml_dir": ml_dir,
              "run_dir": str(Path(run_dir) / name), "config": config} for w in windows for s in seeds]
    with ProcessPoolExecutor(workers) as pool:
        return [r for rs in pool.map(run_world, tasks) for r in rs]
