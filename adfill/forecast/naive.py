"""Phase 1 stand-in forecast: trailing daily average of matching breaks, projected forward.

The average rolls: every break the engine sees is observed (arrival only, never outcome), and each
campaign's rate is recomputed once per day from the last `trailing_days` completed days. It still
ignores seasonality, day-of-week, and the fact that other campaigns compete for the same breaks.
Phase 3 measures what that costs.
"""

from __future__ import annotations

from collections import Counter, deque
from collections.abc import Iterable

from adfill.core.eligibility import matches_targeting
from adfill.core.model import SECONDS_PER_DAY, Break, Campaign

Key = tuple[int, frozenset[str], str]  # (title, genres, device)


class NaiveForecast:
    def __init__(self, history: Iterable[Break], trailing_days: int):
        if trailing_days <= 0:
            raise ValueError("trailing_days must be positive")
        self.trailing_days = trailing_days
        # Counts per (title, genres, device) per completed day: far fewer keys than breaks.
        self._days: deque[tuple[int, Counter[Key]]] = deque()
        self._total: Counter[Key] = Counter()  # sum of self._days
        self._today: tuple[int, Counter[Key]] | None = None
        self._rates: dict[str, float] = {}
        self._rates_day: int | None = None
        for b in history:
            self.observe(b)

    def _roll_to(self, day: int) -> None:
        if self._today is not None and self._today[0] != day:
            if day < self._today[0]:
                raise ValueError("breaks must be observed in time order")
            self._days.append(self._today)
            self._total += self._today[1]
            self._today = None
        while self._days and self._days[0][0] < day - self.trailing_days:
            self._total -= self._days.popleft()[1]

    def observe(self, brk: Break) -> None:
        day = brk.t // SECONDS_PER_DAY
        self._roll_to(day)
        if self._today is None:
            self._today = (day, Counter())
        self._today[1][(brk.title, brk.genres, brk.device)] += 1

    def daily_rate(self, campaign: Campaign, now: int) -> float:
        day = now // SECONDS_PER_DAY
        if day != self._rates_day:
            self._roll_to(day)
            self._rates, self._rates_day = {}, day
        rate = self._rates.get(campaign.id)
        if rate is None:
            n = sum(
                k
                for (title, genres, device), k in self._total.items()
                if matches_targeting(campaign.targeting, genres, device, title)
            )
            rate = self._rates[campaign.id] = n / self.trailing_days
        return rate

    def matching_supply(self, campaign: Campaign, now: int) -> float:
        days_left = max(0, campaign.end - max(now, campaign.start)) / SECONDS_PER_DAY
        return self.daily_rate(campaign, now) * days_left
