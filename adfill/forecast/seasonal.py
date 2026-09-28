"""Trailing level x day-of-week factors.

Viewing is weekly: weekends run 1.25-1.45x the average day. Over a whole flight that averages out;
over the last few days of one it does not, and the last few days are where urgency is decided.
Factors are pooled across all traffic (per-segment factors from two weeks of history are too noisy).
"""

from __future__ import annotations

from collections import Counter

from adfill.core.model import SECONDS_PER_DAY, Campaign
from adfill.forecast.naive import NaiveForecast

# 1970-01-01 was a Thursday; (day + 3) % 7 gives Monday = 0.
_DOW_OFFSET = 3


def dow(day: int) -> int:
    return (day + _DOW_OFFSET) % 7


class SeasonalForecast(NaiveForecast):
    def __init__(self, history, trailing_days: int):
        self._factor_cache: list[float] = [1.0] * 7
        self._factor_day: int | None = None
        super().__init__(history, trailing_days)

    def _factors(self) -> list[float]:
        per_dow: Counter[int] = Counter()
        days_seen: Counter[int] = Counter()
        for day, counts in self._days:
            per_dow[dow(day)] += sum(counts.values())
            days_seen[dow(day)] += 1
        if len(days_seen) < 7:
            return [1.0] * 7
        mean_by_dow = [per_dow[d] / days_seen[d] for d in range(7)]
        overall = sum(mean_by_dow) / 7
        return [m / overall if overall else 1.0 for m in mean_by_dow]

    def matching_supply(self, campaign: Campaign, now: int) -> float:
        rate = self.daily_rate(campaign, now)  # also rolls the window to `now`
        if self._factor_day != self._rates_day:
            self._factor_cache, self._factor_day = self._factors(), self._rates_day
        start, end = max(now, campaign.start), campaign.end
        if end <= start:
            return 0.0
        total, t = 0.0, start
        while t < end:
            day = t // SECONDS_PER_DAY
            nxt = min(end, (day + 1) * SECONDS_PER_DAY)
            total += (nxt - t) / SECONDS_PER_DAY * self._factor_cache[dow(day)]
            t = nxt
        return rate * total
