"""Phase 5: stale counters overshoot a burst; instant counters and a scheduled throttle do not."""

from adfill.core.engine import Engine, Policy
from adfill.core.model import SECONDS_PER_DAY, Break, Campaign, Creative, Targeting
from adfill.forecast.naive import NaiveForecast

T0 = 20_000 * SECONDS_PER_DAY
GOAL = 50


def burst(n=2_000):
    return [Break(f"b{i}", i, 1, frozenset({"Live"}), "tv", T0 + i * 5 // n, 30) for i in range(n)]  # 5 s, in order


def campaign():
    return Campaign("g", "g", "auto", (Creative("g", 30),), GOAL, T0 - SECONDS_PER_DAY, T0 + SECONDS_PER_DAY,
                    Targeting(), 40.0, 40.0)


def run(sync_s=0, throttle="none", expected=None):
    history = [Break(f"h{i}", i, 1, frozenset({"Live"}), "tv", T0 - SECONDS_PER_DAY + i, 30) for i in range(100)]
    e = Engine(Policy.ADFILL, [campaign()], NaiveForecast(history, 1), sync_s=sync_s, throttle=throttle,
               expected_arrivals=expected, seed=1)
    for b in burst():
        e.decide(b)
    return e.delivered["g"]


def test_instant_counters_stop_at_goal():
    assert run() == GOAL


def test_stale_counters_overshoot_a_burst():
    assert run(sync_s=1) > 5 * GOAL


def test_scheduled_throttle_holds_the_goal():
    per_second = 2_000 / 5
    got = run(sync_s=1, throttle="scheduled", expected=lambda c, t: per_second)
    assert GOAL * 0.5 <= got <= GOAL * 1.5
