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
from adfill.forecast.avails import Avails
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
    effective_slots: float | None = None,
    stats: dict | None = None,
) -> list[Campaign]:
    """`content` is required for semantic targeting or brand safety."""
    if (cfg.targeting_mode == "semantic" or cfg.brand_safety != "off") and content is None:
        raise ValueError("semantic targeting and brand safety need a ContentIndex")
    briefs = sorted(BRIEFS)
    # Its own stream: adding semantic targeting must not change the genre-targeted deals of Phase 1.
    brief_rng = np.random.default_rng([cfg.seed, 0xB21E])
    reach_rng = np.random.default_rng([cfg.seed, 0x4EAC])  # Phase 4 draws: own stream (see B7)
    viewers_per_break = (stats or {}).get("viewers_per_break", 1.0)
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
        if reach_rng.random() < cfg.reach_share:
            c = replace(c, goal_type="reach")
        if cfg.freq_cap:
            c = replace(c, freq_cap=cfg.freq_cap, freq_window_s=cfg.freq_window_s)
        sell_through = float(rng.uniform(*cfg.sell_through_range))
        # Booked before the window opens: sized by what the forecast knew then.
        drafts.append((c, sell_through * forecast.matching_supply(c, window_start)))

    everything = Campaign("_all", "_", "_", (), 0, window_start, window_start + window_days * SECONDS_PER_DAY,
                          Targeting(), 0.0, 0.0)
    capacity = forecast.matching_supply(everything, window_start) * slots_per_break
    scale = cfg.guaranteed_book_share * capacity / max(1.0, sum(w for _, w in drafts))
    # A reach deal sells unique viewers: its matching supply in viewers is breaks x viewers-per-break.
    sized = [(c, w * scale * (viewers_per_break if c.goal_type == "reach" else 1.0)) for c, w in drafts]
    out = [replace(c, goal=int(g)) for c, g in sized if int(g) > 0]
    requested = sum(c.goal for c in out)
    if cfg.avails_check:
        out = _check_avails(out, cfg, forecast, window_start, window_days, effective_slots or slots_per_break, stats)
    if stats is not None:
        stats["requested_impressions"] = requested
        stats["booked_impressions"] = sum(c.goal for c in out)
    if cfg.brand_safety == "after_booking":  # sized as if unrestricted, then the rules arrive
        out = [replace(c, targeting=replace(c.targeting, blocked=content.unsafe[c.category])) for c in out]
    return out


def _check_avails(proposed: list[Campaign], cfg: SimConfig, forecast, window_start: int, window_days: int,
                  slots: float, stats: dict | None) -> list[Campaign]:
    """Sell deals in order; each gets what avails can still deliver, or is refused if that is too little."""
    avails = Avails(forecast, window_start, window_days, slots, cfg.avails_margin, cfg.booking_forecast_bias)
    booked, trimmed, refused = [], 0, 0
    for c in proposed:
        can = min(c.goal, avails.deliverable(c))
        if can < cfg.avails_min_fill * c.goal:
            refused += 1
            continue
        trimmed += int(can < c.goal)
        c = replace(c, goal=int(can))
        avails.booked.append(c)
        booked.append(c)
    if stats is not None:
        stats["deals_trimmed"], stats["deals_refused"] = trimmed, refused
    return booked
