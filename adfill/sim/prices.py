"""Programmatic bid prices from the Criteo attribution dataset's per-impression `cost` column.

Each synthetic programmatic advertiser is mapped to one real Criteo campaign and bids by sampling
that campaign's recorded costs, so both the within-advertiser spread and the differences between
advertisers are real. Costs are in undisclosed scaled units, so one global factor maps the pooled
median of the chosen campaigns to `bid_cpm_median`. The shape is data; the level is an assumption.

Costs exist only for impressions that were won (SPEC §4.1), so this is the distribution of clearing
prices, not of bids. Phase 3 handles the censoring; Phase 1 treats clearing prices as bids.
"""

from __future__ import annotations

from functools import cache
from pathlib import Path

import numpy as np
import pandas as pd

DEFAULT_CACHE = Path("data/criteo/costs.parquet")
MIN_IMPRESSIONS = 10_000


def prepare_cache(tsv_gz: Path, out: Path = DEFAULT_CACHE) -> None:
    df = pd.read_csv(tsv_gz, sep="\t", usecols=["campaign", "cost"], dtype={"campaign": "int64", "cost": "float64"})
    out.parent.mkdir(parents=True, exist_ok=True)
    df.astype({"cost": "float32"}).to_parquet(out, index=False)


@cache
def _campaign_costs(path: Path) -> dict[int, np.ndarray]:
    df = pd.read_parquet(path)
    return {int(c): g.to_numpy(np.float64) for c, g in df.groupby("campaign").cost}


class CriteoPrices:
    def __init__(self, n_advertisers: int, median_cpm: float, seed: int, path: Path = DEFAULT_CACHE):
        costs = _campaign_costs(path)
        eligible = sorted(c for c, v in costs.items() if len(v) >= MIN_IMPRESSIONS)
        if len(eligible) < n_advertisers:
            raise ValueError(f"only {len(eligible)} Criteo campaigns have {MIN_IMPRESSIONS}+ impressions")
        rng = np.random.default_rng([seed, 0xC417])
        self.campaigns = [int(c) for c in rng.choice(eligible, n_advertisers, replace=False)]
        self._costs = [costs[c] for c in self.campaigns]
        self.scale = median_cpm / float(np.median(np.concatenate(self._costs)))

    def draw(self, advertiser: np.ndarray, rng: np.random.Generator) -> np.ndarray:
        """CPM for each bid, sampled from its advertiser's Criteo campaign."""
        out = np.empty(len(advertiser))
        for a in np.unique(advertiser):
            mask = advertiser == a
            out[mask] = rng.choice(self._costs[a], mask.sum())
        return out * self.scale
