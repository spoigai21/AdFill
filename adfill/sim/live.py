"""A national live break (SPEC Phase 5): the whole audience hits one ad break within seconds.

The audience is `multiple` x an average day's breaks, all new viewers, arriving uniformly over
`window_s`. The event carries the genre "Live", so genre-targeted deals do not match it; untargeted and
device-targeted deals do, which is what makes a day of their inventory appear at once.
"""

from __future__ import annotations

from dataclasses import replace

import numpy as np
import pandas as pd

from adfill.core.model import SECONDS_PER_DAY
from adfill.sim.breaks import make_breaks, viewer_devices
from adfill.sim.config import SimConfig
from adfill.sim.world import World

LIVE_TITLE = -1
LIVE_GENRES = frozenset({"Live"})
VIEWER_BASE = 10_000_000


def inject_live_event(world: World, cfg: SimConfig, multiple: float, day: int = 10, hour: int = 20,
                      window_s: int = 10, length_s: int = 120) -> tuple[World, dict]:
    per_day = len(world.breaks) / world.window_days
    n = int(multiple * per_day)
    start = world.window_start + day * SECONDS_PER_DAY + hour * 3600
    rng = np.random.default_rng([cfg.seed, 0x11FE, int(multiple * 1000)])
    sessions = pd.DataFrame({
        "viewer": VIEWER_BASE + np.arange(n),
        "title": np.full(n, LIVE_TITLE),
        "t": np.sort(start + rng.integers(0, window_s, n)),
    })
    live_cfg = replace(cfg, breaks_per_session=((1, 1.0),), break_lengths_s=((length_s, 1.0),))
    devices = viewer_devices(sessions.viewer.to_numpy(), cfg)
    live = make_breaks(sessions, {LIVE_TITLE: LIVE_GENRES}, devices, live_cfg, salt=7)
    merged = sorted(world.breaks + live, key=lambda b: (b.t, b.id))
    event = {"start": start, "window_s": window_s, "breaks": n, "arrivals_per_s": round(n / window_s, 1),
             "length_s": length_s}
    return replace(world, breaks=merged), event
