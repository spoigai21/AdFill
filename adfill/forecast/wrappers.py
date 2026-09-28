"""Forecast adjustments that compose with any base forecast."""

from __future__ import annotations

from adfill.core.eligibility import matches_targeting
from adfill.core.model import SECONDS_PER_DAY, Break, Campaign
from adfill.forecast.naive import NaiveForecast


class Biased:
    """Deliberately wrong by a constant factor (SPEC §6's required failure experiment)."""

    def __init__(self, inner, factor: float):
        self.inner, self.factor = inner, factor

    def observe(self, brk: Break) -> None:
        self.inner.observe(brk)

    def matching_supply(self, campaign: Campaign, now: int) -> float:
        return self.factor * self.inner.matching_supply(campaign, now)


class ContentionAdjusted:
    """Supply a campaign can actually obtain, not just supply that matches it.

    A break holds about `slots_per_break` ads (after the ad-load cap). If n guaranteed campaigns whose
    remaining flights overlap this one all match a break, each can expect min(1, slots / n) of it.
    Weighted over the campaign's matching traffic, that fraction scales the base forecast. It ignores
    programmatic competition (the allocator decides that) and campaigns that finish early.
    """

    def __init__(self, inner: NaiveForecast, campaigns: list[Campaign], slots_per_break: float):
        self.inner, self.campaigns, self.slots = inner, campaigns, slots_per_break
        self._match: dict = {}  # key -> indices of campaigns whose targeting matches (flight ignored)
        self._share: dict[str, float] = {}
        self._share_day: int | None = None

    def observe(self, brk: Break) -> None:
        self.inner.observe(brk)

    def _matching(self, key) -> tuple[int, ...]:
        m = self._match.get(key)
        if m is None:
            title, genres, device = key
            m = self._match[key] = tuple(
                i for i, c in enumerate(self.campaigns) if matches_targeting(c.targeting, genres, device, title)
            )
        return m

    def obtainable_share(self, campaign: Campaign, now: int) -> float:
        day = now // SECONDS_PER_DAY
        if day != self._share_day:
            self._share, self._share_day = {}, day
        share = self._share.get(campaign.id)
        if share is not None:
            return share
        lo, hi = max(now, campaign.start), campaign.end
        if hi <= lo:
            return 1.0
        span = hi - lo
        weight = [max(0, min(hi, c.end) - max(lo, c.start)) / span for c in self.campaigns]
        me = self.campaigns.index(campaign)
        num = den = 0.0
        for key, k in self.inner._total.items():
            idx = self._matching(key)
            if me not in idx:
                continue
            n = sum(weight[i] for i in idx)
            num += k * min(1.0, self.slots / n) if n > 0 else k
            den += k
        share = self._share[campaign.id] = num / den if den else 1.0
        return share

    def matching_supply(self, campaign: Campaign, now: int) -> float:
        base = self.inner.matching_supply(campaign, now)
        return base * self.obtainable_share(campaign, now) if base > 0 else base
