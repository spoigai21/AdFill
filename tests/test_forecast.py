import pytest

from adfill.core.model import SECONDS_PER_DAY, Break, Campaign, Creative, Targeting
from adfill.forecast.naive import NaiveForecast
from adfill.forecast.seasonal import SeasonalForecast, dow
from adfill.forecast.wrappers import Biased, ContentionAdjusted

MONDAY = 17_595  # 2018-03-05
WEEKEND_BOOST = 2


def history(days=14, per_day=100, title=1):
    out = []
    for d in range(MONDAY - days, MONDAY):
        n = per_day * (WEEKEND_BOOST if dow(d) >= 5 else 1)
        out += [Break(f"{d}-{i}", i, title, frozenset({"Drama"}), "tv", d * SECONDS_PER_DAY + i, 60) for i in range(n)]
    return out


def campaign(cid, start_day, days, genres=None):
    return Campaign(cid, cid, "auto", (Creative(cid, 15),), 100, start_day * SECONDS_PER_DAY,
                    (start_day + days) * SECONDS_PER_DAY, Targeting(genres), 30.0, 30.0)


def test_seasonal_sees_the_weekend_naive_does_not():
    h = history()
    naive, seasonal = NaiveForecast(h, 14), SeasonalForecast(h, 14)
    weekday, weekend = campaign("a", MONDAY, 1), campaign("b", MONDAY + 5, 1)
    now = MONDAY * SECONDS_PER_DAY
    assert naive.matching_supply(weekday, now) == pytest.approx(naive.matching_supply(weekend, now))
    ratio = seasonal.matching_supply(weekend, now) / seasonal.matching_supply(weekday, now)
    assert ratio == pytest.approx(WEEKEND_BOOST)
    # Over whole weeks the two agree.
    week = campaign("c", MONDAY, 7)
    assert seasonal.matching_supply(week, now) == pytest.approx(naive.matching_supply(week, now))


def test_biased_scales():
    f = NaiveForecast(history(), 14)
    c = campaign("a", MONDAY, 3)
    now = MONDAY * SECONDS_PER_DAY
    assert Biased(f, 1.3).matching_supply(c, now) == pytest.approx(1.3 * f.matching_supply(c, now))


def test_contention_share():
    h = history()
    now = MONDAY * SECONDS_PER_DAY
    alone = [campaign("a", MONDAY, 7)]
    assert ContentionAdjusted(NaiveForecast(h, 14), alone, 2.0).obtainable_share(alone[0], now) == 1.0
    crowd = [campaign(f"c{i}", MONDAY, 7) for i in range(4)]
    f = ContentionAdjusted(NaiveForecast(h, 14), crowd, 2.0)
    assert f.obtainable_share(crowd[0], now) == pytest.approx(0.5)  # 4 campaigns, 2 slots
    other_genre = crowd[:3] + [campaign("x", MONDAY, 7, frozenset({"Comedy"}))]
    f = ContentionAdjusted(NaiveForecast(h, 14), other_genre, 2.0)
    assert f.obtainable_share(other_genre[0], now) == pytest.approx(2 / 3)
    half = crowd[:3] + [campaign("late", MONDAY + 3, 7)]  # overlaps only 4 of 7 remaining days
    f = ContentionAdjusted(NaiveForecast(h, 14), half, 2.0)
    assert f.obtainable_share(half[0], now) == pytest.approx(2 / (3 + 4 / 7))


def test_avails_trims_and_never_oversells():
    from dataclasses import replace

    from adfill.forecast.avails import Avails

    h = history(per_day=100)  # weekdays 100 breaks, weekends 200: 14 days = 1,800 breaks, ~128.6/day
    f = NaiveForecast(h, 14)
    rate = len(h) / 14
    av = Avails(f, MONDAY * SECONDS_PER_DAY, 7, slots_per_break=2.0)
    week = 7 * rate
    a = replace(campaign("a", MONDAY, 7), goal=int(0.9 * week))
    assert av.book(a) == a.goal                        # fits: one ad per break, 90% of breaks
    b = replace(campaign("b", MONDAY, 7), goal=int(0.9 * week))
    assert av.book(b) == b.goal                        # second slot in the same breaks
    c = replace(campaign("c", MONDAY, 7), goal=int(0.5 * week))
    granted = av.book(c)
    assert granted <= int(0.2 * week) + 7              # only the leftover of 2 slots x breaks
    assert sum(x.goal for x in av.booked) <= 2 * week + 7
    too_big = replace(campaign("d", MONDAY, 7), goal=int(2 * week))
    assert av.deliverable(too_big) <= week             # never more than one ad per break


def test_avails_margin_and_bias_scale_capacity():
    from dataclasses import replace

    from adfill.forecast.avails import Avails

    f = NaiveForecast(history(), 14)
    c = replace(campaign("a", MONDAY, 7), goal=10**6)
    full = Avails(f, MONDAY * SECONDS_PER_DAY, 7, 2.0).deliverable(c)
    assert Avails(f, MONDAY * SECONDS_PER_DAY, 7, 2.0, margin=0.2).deliverable(c) == pytest.approx(0.8 * full, rel=0.01)
    assert Avails(f, MONDAY * SECONDS_PER_DAY, 7, 2.0, supply_bias=1.3).deliverable(c) == pytest.approx(1.3 * full, rel=0.01)


def test_kaplan_meier_recovers_censored_distribution_and_winners_only_does_not():
    import numpy as np

    from adfill.forecast.winrate import empirical_cdf, evaluate, kaplan_meier_cdf

    rng = np.random.default_rng(0)
    t = rng.lognormal(np.log(0.02), 0.8, 50_000)
    bids = rng.lognormal(np.log(0.02), 0.5, 50_000)
    grid = np.quantile(bids, np.linspace(0.05, 0.95, 50))
    km = kaplan_meier_cdf(np.minimum(t, bids), bids >= t, grid)
    assert np.max(np.abs(km - empirical_cdf(t, grid))) < 0.02
    r = evaluate(t, bids, grid)
    assert r["kaplan_meier"]["max_abs_error"] < 0.02 < r["winners_only"]["max_abs_error"]


def test_threshold_is_the_least_winning_value():
    from adfill.core.model import Candidate, Kind
    from adfill.forecast.winrate import threshold

    a = Candidate(Kind.PROGRAMMATIC, "a", "a", "auto", 15, 0.02, 20.0)
    b = Candidate(Kind.PROGRAMMATIC, "b", "b", "beer", 15, 0.05, 50.0)
    assert threshold([a, b], 30) == pytest.approx(0.02, rel=1e-3)  # must displace the cheaper ad
    assert threshold([a], 30) <= 1e-6 * 1.01                        # free slot: anything wins
    assert threshold([a, b], 10) == float("inf")                    # break too short
