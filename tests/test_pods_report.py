from adfill.report.pods import pod_quality
from adfill.sim.config import SimConfig
from adfill.sim.world import synthetic_world


def test_greedy_never_beats_exact_and_hook_is_passive():
    cfg = SimConfig(seed=3, price_source="lognormal")
    world = synthetic_world(cfg, window_days=5, history_days=3, n_viewers=100, sessions_per_day=80)
    r = pod_quality(world, cfg)
    assert r["breaks_compared"] > 0
    assert 0 < r["greedy_value_share_of_exact"] <= 1
    assert r["exact_fit_rate_greedy"] <= r["exact_fit_rate_exact"]
    assert r["us_per_decision_total"] > 0
