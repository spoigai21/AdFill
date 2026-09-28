"""Assemble one reproducible simulated world: history, the flight window, the deals, the forecast."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

from adfill.content.index import ContentIndex, content_index
from adfill.core.model import SECONDS_PER_DAY, Break, Campaign
from adfill.core.caps import AdLoadTracker
from adfill.forecast.naive import NaiveForecast
from adfill.forecast.seasonal import SeasonalForecast
from adfill.forecast.wrappers import Biased, ContentionAdjusted
from adfill.sim.breaks import make_breaks, viewer_devices
from adfill.sim.config import SimConfig
from adfill.sim.deals import make_campaigns
from adfill.sim.sessions import load_movielens_sessions, load_titles, synthetic_world_sessions


@dataclass
class World:
    history: list[Break]
    breaks: list[Break]
    campaigns: list[Campaign]
    window_start: int
    window_days: int
    history_days: int
    stats: dict = field(default_factory=dict)

    def make_forecast(self, model: str = "naive", contention: bool = False, bias: float = 1.0):
        """A fresh forecast primed on history. Forecasts learn as they run, so each run needs its own."""
        if model == "naive":
            f = NaiveForecast(self.history, self.history_days)
        elif model == "seasonal":
            f = SeasonalForecast(self.history, self.history_days)
        else:
            raise ValueError(f"unknown forecast model {model!r}")
        if contention:
            f = ContentionAdjusted(f, self.campaigns, self.stats["effective_slots_per_break"])
        return Biased(f, bias) if bias != 1.0 else f


def effective_slots_per_break(history: list[Break], cfg: SimConfig, mean_creative_s: float) -> float:
    """Ads a break really holds once the ad-load cap bites, measured on history assuming full fill."""
    tracker = AdLoadTracker(cfg.max_ad_seconds_per_hour)
    total = 0
    for b in history:
        s = min(b.length_s, tracker.remaining(b.viewer, b.t))
        tracker.record(b.viewer, b.t, s)
        total += s
    return total / max(1, len(history)) / mean_creative_s


def _assemble(sessions: pd.DataFrame, titles, cfg: SimConfig, window_start: int, window_days: int,
              history_days: int, content: ContentIndex | None = None) -> World:
    devices = viewer_devices(sessions.viewer.to_numpy(), cfg)
    in_window = sessions.t >= window_start
    unsafe = content.unsafe if (content is not None and cfg.brand_safety != "off") else None
    stats: dict = {}
    history = make_breaks(sessions[~in_window], titles, devices, cfg, salt=0, unsafe=unsafe)
    breaks = make_breaks(sessions[in_window], titles, devices, cfg, salt=1, unsafe=unsafe, stats=stats)
    forecast = NaiveForecast(history, history_days)
    genre_counts = Counter(g for b in history for g in b.genres)
    genre_pool = [g for g, _ in genre_counts.most_common(12)]
    mean_creative_s = sum(d * w for d, w in cfg.creative_durations_s) / sum(w for _, w in cfg.creative_durations_s)
    slots_per_break = sum(b.length_s for b in history) / max(1, len(history)) / mean_creative_s
    stats["effective_slots_per_break"] = effective_slots_per_break(history, cfg, mean_creative_s)
    campaigns = make_campaigns(cfg, forecast, genre_pool, window_start, window_days, slots_per_break, content,
                               stats["effective_slots_per_break"], stats)
    return World(history, breaks, campaigns, window_start, window_days, history_days, stats)


def movielens_world(ml_dir: Path, cfg: SimConfig, window_start: int, window_days: int,
                    history_days: int, viewer_fraction: float) -> World:
    start = window_start - history_days * SECONDS_PER_DAY
    end = window_start + window_days * SECONDS_PER_DAY
    sessions = load_movielens_sessions(ml_dir, start, end, viewer_fraction, cfg.max_sessions_per_viewer_day, cfg.seed)
    titles = load_titles(ml_dir)
    content = None
    if cfg.targeting_mode == "semantic" or cfg.brand_safety != "off":
        content = content_index(ml_dir, frozenset(titles))
    return _assemble(sessions, titles, cfg, window_start, window_days, history_days, content)


def synthetic_world(cfg: SimConfig, window_days: int = 30, history_days: int = 14, n_viewers: int = 2000,
                    sessions_per_day: float = 1500.0) -> World:
    rng = np.random.default_rng([cfg.seed, 0x5147])
    window_start = 1_700_000_000 - 1_700_000_000 % SECONDS_PER_DAY
    sessions, titles = synthetic_world_sessions(
        rng, n_viewers, 300, window_start - history_days * SECONDS_PER_DAY, history_days + window_days,
        sessions_per_day,
    )
    return _assemble(sessions, titles, cfg, window_start, window_days, history_days)
