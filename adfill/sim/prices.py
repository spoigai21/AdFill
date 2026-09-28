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


SCORED = Path("data/criteo/scored_test.parquet")
RATE_MODELS = ("constant", "logistic_hashed", "gbm", "logistic_hashed_raw", "gbm_raw", "oracle")


@cache
def _scored(path: Path) -> dict[int, pd.DataFrame]:
    df = pd.read_parquet(path)
    return {int(c): g.reset_index(drop=True) for c, g in df.groupby("campaign")}


class CriteoConversions:
    """Performance buyers: each bid is a real Criteo test-period impression, paid only on conversion.

    Advertiser a's CPA is set so its expected CPM at its average conversion rate equals the Phase 1
    anchored price level: CPA_a = CPM_a / 1000 / rate_a. What differs between rate models is only how
    each individual impression is valued; the impressions and their outcomes are identical.
    """

    MIN_TEST_ROWS = 1_000

    def __init__(self, n_advertisers: int, median_cpm: float, seed: int,
                 cost_path: Path = DEFAULT_CACHE, scored_path: Path = SCORED):
        costs, scored = _campaign_costs(cost_path), _scored(scored_path)
        eligible = sorted(c for c, v in costs.items()
                          if len(v) >= MIN_IMPRESSIONS and len(scored.get(c, ())) >= self.MIN_TEST_ROWS)
        if len(eligible) < n_advertisers:
            raise ValueError(f"only {len(eligible)} Criteo campaigns are eligible")
        rng = np.random.default_rng([seed, 0xC0A7])
        self.campaigns = [int(c) for c in rng.choice(eligible, n_advertisers, replace=False)]
        scale = median_cpm / float(np.median(np.concatenate([costs[c] for c in self.campaigns])))
        self._rows = [scored[c] for c in self.campaigns]
        cpm = np.array([scale * float(np.median(costs[c])) for c in self.campaigns])
        rate = np.array([float(r.p_constant.mean()) for r in self._rows])
        self.cpa = cpm / 1000 / rate

    def draw(self, advertiser: np.ndarray, rng: np.random.Generator, rate_model: str, inflation: float = 1.0):
        """Per bid: (cpa, predicted conversion rate, converted). Row choice is independent of the model."""
        if rate_model not in RATE_MODELS:
            raise ValueError(f"unknown rate_model {rate_model!r}")
        cpa = np.empty(len(advertiser))
        p = np.empty(len(advertiser))
        y = np.zeros(len(advertiser), dtype=bool)
        for a in np.unique(advertiser):
            mask = advertiser == a
            rows = self._rows[a]
            pick = rng.integers(0, len(rows), mask.sum())
            conv = rows.conversion.to_numpy()[pick].astype(bool)
            col = conv.astype(float) if rate_model == "oracle" else rows[f"p_{rate_model}"].to_numpy()[pick]
            cpa[mask], p[mask], y[mask] = self.cpa[a], np.minimum(col * inflation, 1.0), conv
        return cpa, p, y
