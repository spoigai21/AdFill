"""Synthesize the guaranteed book: who bought what, for how long, and how many impressions.

Each deal's size starts as a share of its own forecast matching supply. Deals overlap, so the whole
book is then scaled to `guaranteed_book_share` of the forecast ad slots in the window. Individual narrow
deals can still end up oversold; the book as a whole is not.
"""

from __future__ import annotations

from dataclasses import replace

import numpy as np

from adfill.core.model import SECONDS_PER_DAY, Campaign, Creative, Targeting
from adfill.content.index import ContentIndex
from adfill.content.rules import BRIEFS
from adfill.forecast.base import SupplyForecast
from adfill.sim.config import CATEGORIES, SimConfig


def make_campaigns(
    cfg: SimConfig,
    forecast: SupplyForecast,
    genre_pool: list[str],
    window_start: int,
    window_days: int,
    slots_per_break: float,
    content: ContentIndex | None = None,
) -> list[Campaign]:
    """`content` is required for semantic targeting or brand safety."""
    if (cfg.targeting_mode == "semantic" or cfg.brand_safety != "off") and content is None:
        raise ValueError("semantic targeting and brand safety need a ContentIndex")
    briefs = sorted(BRIEFS)
    # Its own stream: adding semantic targeting must not change the genre-targeted deals of Phase 1.
    brief_rng = np.random.default_rng([cfg.seed, 0xB21E])
    rng = np.random.default_rng([cfg.seed, 0xDEA1])
    drafts: list[tuple[Campaign, float]] = []
    for i in range(cfg.n_campaigns):
        lo, hi = (min(d, window_days) for d in cfg.flight_days_range)
        flight = int(rng.integers(lo, hi + 1))
        start = window_start + int(rng.integers(0, window_days - flight + 1)) * SECONDS_PER_DAY
        genres = titles = brief = None
        if rng.random() < cfg.genre_targeted_share:
            k = int(rng.integers(cfg.genres_per_campaign_range[0], cfg.genres_per_campaign_range[1] + 1))
            picked = rng.choice(genre_pool, size=min(k, len(genre_pool)), replace=False).tolist()
            brief_pick = int(brief_rng.integers(len(briefs)))
            if cfg.targeting_mode == "semantic":
                brief = briefs[brief_pick]
                titles = content.briefs[brief]
            else:
                genres = frozenset(picked)
        devices = frozenset({"tv"}) if rng.random() < cfg.device_targeted_share else None
        durations = [15, 30] if rng.random() < 0.5 else [int(rng.choice([15, 30]))]
        cpm = round(float(rng.uniform(*cfg.campaign_cpm_range)), 2)
        category = CATEGORIES[int(rng.integers(len(CATEGORIES)))]
        blocked = content.unsafe[category] if cfg.brand_safety == "on" else frozenset()
        c = Campaign(
            id=f"g{i}",
            advertiser=f"g{i}",
            category=category,
            creatives=tuple(Creative(f"g{i}-{d}", d) for d in durations),
            goal=0,
            start=start,
            end=start + flight * SECONDS_PER_DAY,
            targeting=Targeting(genres, devices, titles, blocked, brief),
            cpm=cpm,
            makegood_cpm=round(cpm * cfg.makegood_ratio, 2),
        )
        sell_through = float(rng.uniform(*cfg.sell_through_range))
        # Booked before the window opens: sized by what the forecast knew then.
        drafts.append((c, sell_through * forecast.matching_supply(c, window_start)))

    everything = Campaign("_all", "_", "_", (), 0, window_start, window_start + window_days * SECONDS_PER_DAY,
                          Targeting(), 0.0, 0.0)
    capacity = forecast.matching_supply(everything, window_start) * slots_per_break
    scale = cfg.guaranteed_book_share * capacity / max(1.0, sum(w for _, w in drafts))
    out = [replace(c, goal=int(w * scale)) for c, w in drafts if int(w * scale) > 0]
    if cfg.brand_safety == "after_booking":  # sized as if unrestricted, then the rules arrive
        out = [replace(c, targeting=replace(c.targeting, blocked=content.unsafe[c.category])) for c in out]
    return out
