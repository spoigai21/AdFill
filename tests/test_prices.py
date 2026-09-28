import numpy as np
import pytest

from adfill.sim.prices import DEFAULT_CACHE, CriteoPrices

pytestmark = pytest.mark.skipif(not DEFAULT_CACHE.exists(), reason="Criteo cache not built")


def test_pooled_median_is_anchored_and_deterministic():
    p = CriteoPrices(60, 18.0, seed=1)
    adv = np.random.default_rng(0).integers(0, 60, 200_000)
    cpm = p.draw(adv, np.random.default_rng(1))
    assert np.median(cpm) == pytest.approx(18.0, rel=0.1)
    assert CriteoPrices(60, 18.0, seed=1).campaigns == p.campaigns
    assert CriteoPrices(60, 18.0, seed=2).campaigns != p.campaigns
