"""The interface the allocator prices against. Phase 1 uses `naive`; Phase 3 replaces it."""

from __future__ import annotations

from typing import Protocol

from adfill.core.model import Break, Campaign


class SupplyForecast(Protocol):
    def observe(self, brk: Break) -> None:
        """A break arrived. Forecasts may learn from arrivals, never from decisions."""
        ...

    def matching_supply(self, campaign: Campaign, now: int) -> float:
        """Expected breaks this campaign could serve into, from `now` to the end of its flight."""
        ...
