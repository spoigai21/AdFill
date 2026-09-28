from collections import Counter

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from adfill.core.model import Candidate, Kind
from adfill.core.pod import (
    EMPTY_POD,
    is_legal_pod,
    order_pod,
    solve_brute,
    solve_exact,
    solve_greedy,
)

CATEGORIES = ["auto", "beer", "telecom", "retail"]


def cand(ref, adv, cat, dur, value):
    return Candidate(Kind.PROGRAMMATIC, ref, adv, cat, dur, value, value * 1000)


@st.composite
def catalogues(draw):
    n_adv = draw(st.integers(1, 6))
    adv_cat = {f"a{i}": draw(st.sampled_from(CATEGORIES)) for i in range(n_adv)}
    items = draw(
        st.lists(
            st.tuples(
                st.sampled_from(sorted(adv_cat)),
                st.sampled_from([15, 30, 45, 60]),
                st.floats(0, 50, allow_nan=False).map(lambda v: round(v, 3)),
            ),
            max_size=9,
        )
    )
    cands = [cand(f"c{i}", a, adv_cat[a], d, v) for i, (a, d, v) in enumerate(items)]
    length = draw(st.sampled_from([15, 30, 60, 90, 120]))
    tolerance = draw(st.sampled_from([0, 0, 15]))
    return cands, length, tolerance


@settings(max_examples=3000, deadline=None)
@given(catalogues())
def test_exact_matches_brute_force(case):
    cands, length, tol = case
    dp, bf = solve_exact(cands, length, tol), solve_brute(cands, length, tol)
    assert (dp is None) == (bf is None)
    if dp is not None:
        assert dp.value == pytest.approx(bf.value, abs=1e-6)
        assert is_legal_pod(dp, length, tol)


@settings(max_examples=1000, deadline=None)
@given(catalogues())
def test_greedy_never_beats_exact_and_is_ordered_legally(case):
    cands, length, _ = case
    g = solve_greedy(cands, length)
    assert g.duration_s <= length
    assert all(a.category != b.category for a, b in zip(g.items, g.items[1:]))
    exact = solve_exact(cands, length, tolerance=length)  # same feasible region as greedy
    assert g.value <= exact.value + 1e-6


@settings(max_examples=2000, deadline=None)
@given(st.lists(st.sampled_from(CATEGORIES), max_size=10))
def test_order_pod_separates_whenever_possible(cats):
    items = [cand(f"c{i}", f"a{i}", c, 15, float(i)) for i, c in enumerate(cats)]
    arrangeable = all(k <= (len(cats) + 1) // 2 for k in Counter(cats).values())
    if not arrangeable:
        with pytest.raises(ValueError):
            order_pod(items)
        return
    pod = order_pod(items)
    assert sorted(c.ref for c in pod.items) == sorted(c.ref for c in items)
    assert all(a.category != b.category for a, b in zip(pod.items, pod.items[1:]))


def test_one_ad_per_advertiser():
    cands = [cand("x", "a", "auto", 30, 10), cand("y", "a", "auto", 30, 9)]
    assert solve_exact(cands, 60) is None
    assert [c.ref for c in solve_exact(cands, 30).items] == ["x"]


def test_competitive_separation_forces_lower_value():
    cands = [
        cand("a1", "a", "auto", 15, 10),
        cand("b1", "b", "auto", 15, 10),
        cand("c1", "c", "auto", 15, 10),
        cand("d1", "d", "beer", 15, 1),
    ]
    # three autos in a 45s break can never be separated; two autos + beer can.
    pod = solve_exact(cands, 45)
    assert pod.value == 21 and [c.category for c in pod.items] == ["auto", "beer", "auto"]


def test_empty_break():
    assert solve_exact([], 0) == EMPTY_POD
    assert solve_exact([], 30) is None


def test_advertiser_in_two_categories_is_rejected():
    with pytest.raises(ValueError):
        solve_exact([cand("x", "a", "auto", 15, 1), cand("y", "a", "beer", 15, 1)], 30)
