"""Price a promise: how likely is skipping this slot to turn into an undelivered impression?

`required_win_share = debt / forecast matching supply` is the control variable (SPEC §2.2). The curve
mapping it to urgency is flat while slack exists and steep near 1. Its shape is a tunable parameter
whose effect on the headline result is reported, not hidden.
"""

from __future__ import annotations

from dataclasses import dataclass

# A share at or above 1 means the promise cannot be met even by winning every matching slot.
# Urgency is pinned high enough that the campaign takes every slot it can.
OVERSOLD_URGENCY = 100.0


@dataclass(frozen=True)
class UrgencyCurve:
    """urgency(s) = s ** exponent for s in [0, 1). Higher exponent = flatter early, steeper late."""

    exponent: float = 0.5

    def __call__(self, share: float) -> float:
        if share >= 1.0:
            return OVERSOLD_URGENCY
        if share <= 0.0:
            return 0.0
        return share**self.exponent


def required_win_share(debt: int, forecast_supply: float) -> float:
    if debt <= 0:
        return 0.0
    if forecast_supply <= 0:
        return float("inf")
    return debt / forecast_supply
