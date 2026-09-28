"""Run one policy over a world and append every decision to a JSONL log."""

from __future__ import annotations

import json
import time
from pathlib import Path

from adfill.core.caps import AdLoadTracker
from adfill.core.engine import Decision, Engine, Policy
from adfill.core.urgency import UrgencyCurve
from adfill.sim.config import SimConfig
from adfill.sim.world import World


def decision_row(d: Decision) -> dict:
    return {
        "break": d.brk.id,
        "t": d.brk.t,
        "viewer": d.brk.viewer,
        "requested_s": d.brk.length_s,
        "length_s": d.length_s,
        "filled_s": d.pod.duration_s,
        "underfilled": d.underfilled,
        "ads": [
            {"kind": a.kind.value, "ref": a.ref, "advertiser": a.advertiser, "category": a.category,
             "duration_s": a.duration_s, "price_cpm": a.price_cpm, "value": a.value, "paid": a.paid}
            for a in d.pod.items
        ],
    }


def run_policy(world: World, policy: Policy, cfg: SimConfig, log_path: Path) -> tuple[Engine, float]:
    """Returns the engine (for its counters) and mean decision time in microseconds."""
    engine = Engine(
        policy,
        world.campaigns,
        world.make_forecast(cfg.forecast_model, cfg.forecast_contention, cfg.forecast_bias),
        UrgencyCurve(cfg.urgency_exponent),
        AdLoadTracker(cfg.max_ad_seconds_per_hour),
        cfg.pod_tolerance_s,
    )
    log_path.parent.mkdir(parents=True, exist_ok=True)
    spent = 0.0
    with log_path.open("w") as f:
        for brk in world.breaks:
            t0 = time.perf_counter()
            d = engine.decide(brk)
            spent += time.perf_counter() - t0
            f.write(json.dumps(decision_row(d), separators=(",", ":")) + "\n")
    return engine, 1e6 * spent / max(1, len(world.breaks))
