import math

from adfill.core.urgency import OVERSOLD_URGENCY, UrgencyCurve, required_win_share


def test_required_win_share():
    assert required_win_share(0, 100) == 0.0
    assert required_win_share(50, 100) == 0.5
    assert math.isinf(required_win_share(1, 0))


def test_curve_is_monotone_and_pins_oversold():
    for e in (0.5, 1.0, 4.0):
        u = UrgencyCurve(e)
        xs = [i / 100 for i in range(100)]
        assert all(u(a) <= u(b) for a, b in zip(xs, xs[1:]))
        assert u(1.0) == u(3.0) == OVERSOLD_URGENCY


def test_steeper_curve_is_flatter_while_slack():
    assert UrgencyCurve(4.0)(0.3) < UrgencyCurve(1.0)(0.3)
