from pathlib import Path

import pytest

from adfill.content.genome import load_genome
from adfill.content.rules import BRIEFS, SAFETY_RULES, brief_titles, unsafe_titles

ML = Path("data/ml-25m")
pytestmark = pytest.mark.skipif(not (ML / "genome-scores.csv").exists(), reason="MovieLens not present")


@pytest.fixture(scope="module")
def genome():
    return load_genome(ML)


def test_every_rule_and_brief_tag_exists(genome):
    for tags in BRIEFS.values():
        genome.score(tags)  # raises on an unknown tag
    for rules in SAFETY_RULES.values():
        assert set(rules) <= set(genome.tags)


def test_briefs_are_neither_empty_nor_everything(genome):
    for brief in BRIEFS:
        n = len(brief_titles(genome, brief))
        assert 20 < n < 0.5 * len(genome.titles), brief


def test_unverified_titles_are_refused(genome):
    unknown = frozenset({-1, -2})
    refused = unsafe_titles(genome, "retail", frozenset(genome.titles.tolist()) | unknown)
    assert unknown <= refused
    # Pharma refuses strictly more than the shared floor.
    everyone = unsafe_titles(genome, "retail", frozenset())
    assert everyone < unsafe_titles(genome, "pharma", frozenset())


def test_safety_modes_share_one_deal_stream():
    """Same seed: safety off, on and after_booking must yield the same deals apart from blocked titles."""
    from dataclasses import replace
    from datetime import datetime, timezone

    from adfill.sim.config import SimConfig
    from adfill.sim.world import movielens_world

    start = int(datetime(2018, 3, 1, tzinfo=timezone.utc).timestamp())
    worlds = {m: movielens_world(ML, SimConfig(seed=1, price_source="lognormal", brand_safety=m), start, 10, 7, 0.1)
              for m in ("off", "on", "after_booking")}
    strip = lambda cs: [(c.id, c.category, c.start, c.end, c.targeting.genres, c.targeting.devices) for c in cs]
    assert strip(worlds["off"].campaigns) == strip(worlds["on"].campaigns) == strip(worlds["after_booking"].campaigns)
    # after_booking is sized exactly like off, then restricted
    assert [c.goal for c in worlds["off"].campaigns] == [c.goal for c in worlds["after_booking"].campaigns]
    assert all(c.targeting.blocked for c in worlds["after_booking"].campaigns)
    assert sum(c.goal for c in worlds["on"].campaigns) != sum(c.goal for c in worlds["off"].campaigns)
    assert replace(worlds["off"].campaigns[0], goal=0).targeting.blocked == frozenset()
