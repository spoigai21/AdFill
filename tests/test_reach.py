"""Phase 4 invariants: frequency caps, reach goals, and billing under duplicated, reordered reports."""

from collections import Counter

import pytest

from adfill.core.engine import Policy
from adfill.report.beacons import audit
from adfill.report.delivery import headline
from adfill.report.reach import reach_report
from adfill.sim.config import SimConfig
from adfill.sim.runner import run_policy
from adfill.sim.world import synthetic_world

CFG = SimConfig(seed=11, price_source="lognormal", reach_share=0.3, freq_cap=2)


@pytest.fixture(scope="module")
def world():
    # Few viewers, many sessions: the same viewer comes back often, so caps and reach bind.
    return synthetic_world(CFG, window_days=10, history_days=5, n_viewers=60, sessions_per_day=200)


@pytest.fixture(scope="module", params=list(Policy))
def run(request, world, tmp_path_factory):
    log = tmp_path_factory.mktemp(request.param.value) / "log.jsonl"
    engine, _ = run_policy(world, request.param, CFG, log)
    return engine, log


def test_world_has_both_goal_types_and_caps(world):
    kinds = Counter(c.goal_type for c in world.campaigns)
    assert kinds["reach"] > 0 and kinds["impressions"] > 0
    assert all(c.freq_cap == 2 for c in world.campaigns)


def test_caps_never_exceeded_and_they_bind(world, run):
    engine, log = run
    r = reach_report(log, world.campaigns, cap=2)
    assert r["violations_of_own_caps"] == 0
    assert any(row["max_frequency"] > 2 for row in r["campaigns"])  # over the flight, not per day: caps are per 24h


def test_reach_deals_never_serve_a_viewer_twice(world, run):
    _, log = run
    r = reach_report(log, world.campaigns)
    for row in r["campaigns"]:
        if row["goal_type"] == "reach":
            assert row["impressions"] == row["reach"]


def test_reach_progress_is_unique_viewers(world, run):
    engine, log = run
    _, delivered = headline(log, world.campaigns)
    assert dict(delivered) == engine.delivered
    for c in world.campaigns:
        if c.goal_type == "reach":
            assert engine.delivered[c.id] == len(engine.reached[c.id]) <= c.goal


def test_billing_is_exact_under_duplicated_reordered_reports(world, run):
    _, log = run
    caps = {c.id: (c.freq_cap, c.freq_window_s) for c in world.campaigns}
    a = audit(log, caps, CFG.max_ad_seconds_per_hour, dup_rate=0.05, max_delay_s=3600, seed=1)
    assert a["reconciled"]["overcount"] == 0
    assert a["reconciled"]["campaigns_miscounted"] == 0
    assert a["reconciled"]["frequency_cap_violations"] == 0
    assert a["reconciled"]["viewers_over_ad_load"] == 0
    assert a["naive"]["overcount"] > 0.03  # the negative control does see the duplicates
