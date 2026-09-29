"""Avails: how much of a proposed deal can still be delivered, given what is already sold (SPEC §6).

The forecast supply is cut into cells: (which deals can serve this traffic, day). A deal can take at most
one ad per break, so its edge into a cell carries at most the cell's breaks; a cell holds at most
breaks x slots-per-break guaranteed ads in total. Booked goals plus the proposed one flow from a source
through deals and cells to a sink. The proposed deal can be sold up to the extra flow the network carries
beyond what is already booked. Augmenting paths never reduce flow already on a source edge, so the deals
booked earlier stay fully deliverable.

Brand safety, device and semantic targeting all enter through eligibility, so a refusal rule shrinks
the cells it touches and the check sees it.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import replace

import numpy as np
from scipy.sparse import csr_matrix
from scipy.sparse.csgraph import maximum_flow

from adfill.core.eligibility import matches_targeting
from adfill.core.model import SECONDS_PER_DAY, Campaign
from adfill.forecast.naive import NaiveForecast
from adfill.forecast.seasonal import SeasonalForecast, dow


class Avails:
    def __init__(self, forecast: NaiveForecast, window_start: int, window_days: int, slots_per_break: float,
                 margin: float = 0.0, supply_bias: float = 1.0):
        """`margin` holds back a share of capacity against forecast error; `supply_bias` misstates supply."""
        self.slots = slots_per_break
        self.first_day = window_start // SECONDS_PER_DAY
        self.days = window_days
        forecast._roll_to(self.first_day)  # fold the last history day in; otherwise it is left out
        keep = (1.0 - margin) * supply_bias
        factors = forecast._factors() if isinstance(forecast, SeasonalForecast) else [1.0] * 7
        self._day_factor = [factors[dow(self.first_day + d)] for d in range(window_days)]
        self._keys = [(k, keep * n / forecast.trailing_days) for k, n in forecast._total.items()]
        self.booked: list[Campaign] = []

    def _network(self, campaigns: list[Campaign]):
        """Build and solve the flow network; returns max flow value."""
        signature_rate: dict[frozenset[int], float] = defaultdict(float)
        for (title, genres, device), rate in self._keys:
            sig = frozenset(i for i, c in enumerate(campaigns)
                            if matches_targeting(c.targeting, genres, device, title))
            if sig:
                signature_rate[sig] += rate
        n_c = len(campaigns)
        src, sink = 0, 1
        edges: list[tuple[int, int, int]] = []
        for i, c in enumerate(campaigns):
            edges.append((src, 2 + i, c.goal))
        node = 2 + n_c
        for sig, rate in signature_rate.items():
            for d in range(self.days):
                day_start = (self.first_day + d) * SECONDS_PER_DAY
                live = [i for i in sig if campaigns[i].start < day_start + SECONDS_PER_DAY
                        and campaigns[i].end > day_start]
                if not live:
                    continue
                breaks = rate * self._day_factor[d]
                for i in live:
                    c = campaigns[i]
                    overlap = (min(c.end, day_start + SECONDS_PER_DAY) - max(c.start, day_start)) / SECONDS_PER_DAY
                    edges.append((2 + i, node, int(breaks * overlap)))
                edges.append((node, sink, int(breaks * self.slots)))
                node += 1
        rows, cols, caps = zip(*edges, strict=True)
        graph = csr_matrix((np.array(caps, dtype=np.int32), (rows, cols)), shape=(node, node))
        return int(maximum_flow(graph, src, sink).flow_value)

    def deliverable(self, proposed: Campaign) -> int:
        """Largest goal for `proposed` that keeps every booked deal deliverable."""
        already = sum(c.goal for c in self.booked)
        return int(max(0, self._network(self.booked + [proposed]) - already))

    def book(self, proposed: Campaign) -> int:
        granted = min(proposed.goal, self.deliverable(proposed))
        if granted > 0:
            self.booked.append(replace(proposed, goal=granted))
        return granted
