import numpy as np
import pandas as pd
import pytest

from adfill.bandit.creative import simulate
from adfill.bandit.ope import estimate


def test_ope_recovers_a_known_policy_value():
    rng = np.random.default_rng(0)
    n_items, n = 5, 400_000
    rates = np.array([0.01, 0.02, 0.03, 0.04, 0.05])
    hours = pd.to_datetime(["2020-01-01 00:00", "2020-01-01 01:00"], utc=True)
    log = pd.DataFrame({
        "hour": hours[rng.integers(0, 2, n)],
        "position": rng.integers(1, 3, n),
        "item_id": rng.integers(0, n_items, n),
        "propensity_score": 1 / n_items,
    })
    log["click"] = (rng.random(n) < rates[log.item_id]).astype(int)
    target = np.array([0.05, 0.05, 0.1, 0.3, 0.5])  # evaluation policy, same in every cell
    idx = pd.MultiIndex.from_product([hours, [1, 2]], names=["hour", "position"])
    pi_e = pd.DataFrame(np.tile(target, (len(idx), 1)), index=idx, columns=range(n_items))
    truth = float(target @ rates)
    est = estimate(log, pi_e)
    for k in ("ips", "snips", "dm", "dr"):
        assert est[k] == pytest.approx(truth, rel=0.03), k
    assert est["naive"] == pytest.approx(rates.mean(), rel=0.03)  # the naive estimate answers another question


def test_creative_bandit_ordering_on_a_clear_problem():
    truth = np.array([0.002, 0.003, 0.004, 0.005, 0.02, 0.003, 0.004])
    prior_n = np.full(len(truth), 2000.0)
    prior_c = truth * prior_n
    r = simulate(truth, prior_c, prior_n, n_impressions=100_000, reps=100, seed=0)
    assert r["oracle"]["regret_vs_oracle"] == 0
    assert r["ts"]["regret_share"] < r["uniform"]["regret_share"]
    assert r["ts"]["goal_met_share"] >= r["uniform"]["goal_met_share"]
