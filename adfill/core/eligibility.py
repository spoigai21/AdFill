"""Can a guaranteed campaign serve into a break? Flight dates and targeting."""

from __future__ import annotations

from adfill.core.model import Break, Campaign, Targeting


def matches_targeting(targeting: Targeting, genres: frozenset[str], device: str, title: int) -> bool:
    if targeting.genres is not None and not (targeting.genres & genres):
        return False
    if targeting.devices is not None and device not in targeting.devices:
        return False
    if targeting.titles is not None and title not in targeting.titles:
        return False
    return title not in targeting.blocked


def in_flight(campaign: Campaign, t: int) -> bool:
    return campaign.start <= t < campaign.end


def eligible(campaign: Campaign, brk: Break) -> bool:
    return in_flight(campaign, brk.t) and matches_targeting(
        campaign.targeting, brk.genres, brk.device, brk.title
    )
