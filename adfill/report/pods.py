"""Pod quality (SPEC §3, §8): how far greedy falls below the exact solver, and what exact costs.

Runs AdFill over one world. At every break the exact solver's input is also handed to the greedy
baseline; greedy's answer is measured but never served, so both see identical state.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

from adfill.core.caps import AdLoadTracker
from adfill.core.engine import Engine, Policy
from adfill.core.model import Break, Candidate
from adfill.core.pod import solve_exact, solve_greedy
from adfill.core.urgency import UrgencyCurve
from adfill.sim.config import SimConfig
from adfill.sim.world import World


@dataclass
class _Tally:
    breaks: int = 0
    exact_value: float = 0.0
    greedy_value: float = 0.0
    greedy_worse: int = 0
    exact_fit_exact: int = 0
    exact_fit_greedy: int = 0
    exact_s: float = 0.0
    greedy_s: float = 0.0
    worst_gap: float = 0.0

    def observe(self, brk: Break, length: int, cands: list[Candidate]) -> None:
        if not cands or length <= 0:
            return
        t0 = time.perf_counter()
        exact = solve_exact(cands, length, tolerance=length)  # best pod <= length: same region as greedy
        t1 = time.perf_counter()
        greedy = solve_greedy(cands, length)
        t2 = time.perf_counter()
        self.breaks += 1
        self.exact_s += t1 - t0
        self.greedy_s += t2 - t1
        self.exact_value += exact.value
        self.greedy_value += greedy.value
        self.exact_fit_exact += solve_exact(cands, length) is not None
        self.exact_fit_greedy += greedy.duration_s == length
        if greedy.value < exact.value - 1e-9:
            self.greedy_worse += 1
            gap = 1 - greedy.value / exact.value
            self.worst_gap = max(self.worst_gap, gap)


def pod_quality(world: World, cfg: SimConfig) -> dict:
    tally = _Tally()
    engine = Engine(Policy.ADFILL, world.campaigns, world.make_forecast(), UrgencyCurve(cfg.urgency_exponent),
                    AdLoadTracker(cfg.max_ad_seconds_per_hour), cfg.pod_tolerance_s, on_candidates=tally.observe)
    for brk in world.breaks:
        engine.decide(brk)

    # Stage costs from a clean run with no hook, so instrumentation does not inflate them.
    clean = Engine(Policy.ADFILL, world.campaigns, world.make_forecast(), UrgencyCurve(cfg.urgency_exponent),
                   AdLoadTracker(cfg.max_ad_seconds_per_hour), cfg.pod_tolerance_s)
    for brk in world.breaks:
        clean.decide(brk)
    n = len(world.breaks)
    t = tally
    return {
        "breaks_compared": t.breaks,
        "greedy_value_share_of_exact": round(t.greedy_value / t.exact_value, 4),
        "breaks_where_greedy_worse": t.greedy_worse,
        "breaks_where_greedy_worse_share": round(t.greedy_worse / t.breaks, 4),
        "worst_single_break_gap": round(t.worst_gap, 4),
        "exact_fit_rate_exact": round(t.exact_fit_exact / t.breaks, 4),
        "exact_fit_rate_greedy": round(t.exact_fit_greedy / t.breaks, 4),
        "us_exact_per_break": round(1e6 * t.exact_s / t.breaks, 1),
        "us_greedy_per_break": round(1e6 * t.greedy_s / t.breaks, 1),
        "us_per_decision_by_stage": {k: round(1e6 * v / n, 1) for k, v in clean.stage_s.items()},
        "us_per_decision_total": round(1e6 * sum(clean.stage_s.values()) / n, 1),
    }
