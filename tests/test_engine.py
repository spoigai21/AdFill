"""Invariants over full simulated runs (SPEC §10)."""

import json
from collections import defaultdict, deque

import pytest

from adfill.core.engine import Policy
from adfill.report.delivery import headline
from adfill.sim.config import SimConfig
from adfill.sim.runner import run_policy
from adfill.sim.world import synthetic_world

CFG = SimConfig(seed=7, price_source="lognormal")  # tests must not need the Criteo download


@pytest.fixture(scope="module")
def world():
    return synthetic_world(CFG, window_days=10, history_days=5, n_viewers=300, sessions_per_day=200)


@pytest.fixture(scope="module", params=list(Policy))
def run(request, world, tmp_path_factory):
    log = tmp_path_factory.mktemp(request.param.value) / "log.jsonl"
    engine, _ = run_policy(world, request.param, CFG, log)
    rows = [json.loads(line) for line in log.open()]
    return engine, log, rows


def test_every_break_is_logged(world, run):
    _, _, rows = run
    assert [r["break"] for r in rows] == [b.id for b in world.breaks]


def test_no_campaign_exceeds_goal(world, run):
    engine, _, _ = run
    for c in world.campaigns:
        assert engine.delivered[c.id] <= c.goal


def test_billed_equals_logged(world, run):
    engine, log, _ = run
    _, delivered = headline(log, world.campaigns)
    assert {c.id: delivered[c.id] for c in world.campaigns} == engine.delivered


def test_pods_are_legal(run):
    _, _, rows = run
    for r in rows:
        ads = r["ads"]
        assert r["filled_s"] == sum(a["duration_s"] for a in ads) <= r["length_s"] <= r["requested_s"]
        assert len({a["advertiser"] for a in ads}) == len(ads)
        assert all(a["category"] != b["category"] for a, b in zip(ads, ads[1:]))
        if not r["underfilled"]:
            assert r["filled_s"] == r["length_s"]


def test_ad_load_cap_holds(run):
    _, _, rows = run
    served = defaultdict(deque)
    for r in rows:
        q = served[r["viewer"]]
        while q and q[0][0] <= r["t"] - 3600:
            q.popleft()
        q.append((r["t"], r["filled_s"]))
        assert sum(s for _, s in q) <= CFG.max_ad_seconds_per_hour


def test_same_seed_same_log(world, tmp_path):
    a, b = tmp_path / "a.jsonl", tmp_path / "b.jsonl"
    run_policy(world, Policy.ADFILL, CFG, a)
    run_policy(world, Policy.ADFILL, CFG, b)
    assert a.read_bytes() == b.read_bytes()


def test_same_seed_same_world(world):
    again = synthetic_world(CFG, window_days=10, history_days=5, n_viewers=300, sessions_per_day=200)
    assert again.breaks == world.breaks and again.campaigns == world.campaigns


def test_book_is_sized_to_capacity(world):
    """Regression: deals booked before the window must be sized from pre-window history (BUG_LOG B4)."""
    promised = sum(c.goal for c in world.campaigns)
    breaks = len(world.breaks)
    slots = breaks * (sum(b.length_s for b in world.breaks) / breaks) / 22.5
    assert 0.25 * slots < promised < 0.6 * slots


def test_genre_deals_do_not_depend_on_the_brief_library(monkeypatch):
    """Regression (BUG_LOG B7): the semantic-brief draw must not shift the genre deals' random stream."""
    import adfill.sim.deals as deals

    kw = dict(window_days=10, history_days=5, n_viewers=300, sessions_per_day=200)
    before = synthetic_world(CFG, **kw).campaigns
    monkeypatch.setattr(deals, "BRIEFS", {"only_one": ("funny",)})
    assert synthetic_world(CFG, **kw).campaigns == before
