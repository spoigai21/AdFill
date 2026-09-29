"""Turn sessions into ad breaks and attach the programmatic bids that arrive for each."""

from __future__ import annotations

import numpy as np
import pandas as pd

from adfill.core.model import Bid, Break, Creative
from adfill.sim.config import CATEGORIES, SimConfig
from adfill.sim.prices import CriteoConversions, CriteoPrices


def _choice(rng: np.random.Generator, table: tuple[tuple, ...], size: int) -> np.ndarray:
    values, probs = zip(*table, strict=True)
    return np.asarray(values)[rng.choice(len(values), size=size, p=np.asarray(probs) / sum(probs))]


def viewer_devices(viewers: np.ndarray, cfg: SimConfig) -> dict[int, str]:
    """Each viewer watches on one device class for the whole run."""
    viewers = np.unique(viewers)
    rng = np.random.default_rng([cfg.seed, 0xDE71])
    return dict(zip(viewers.tolist(), _choice(rng, cfg.device_mix, len(viewers)).tolist(), strict=True))


def make_breaks(
    sessions: pd.DataFrame,
    titles: dict[int, frozenset[str]],
    devices: dict[int, str],
    cfg: SimConfig,
    salt: int,
    unsafe: dict[str, frozenset[int]] | None = None,
    stats: dict | None = None,
) -> list[Break]:
    """`unsafe` (category -> refused titles) drops bids that brand safety forbids, after all draws."""
    rng = np.random.default_rng([cfg.seed, 0xB4EA, salt])

    n_per = _choice(rng, cfg.breaks_per_session, len(sessions))
    idx = np.repeat(np.arange(len(sessions)), n_per)
    k = np.arange(len(idx)) - np.repeat(np.cumsum(n_per) - n_per, n_per)  # break number within session
    viewer = sessions.viewer.to_numpy()[idx]
    title = sessions.title.to_numpy()[idx]
    t = sessions.t.to_numpy()[idx] + k * cfg.break_spacing_s
    length = _choice(rng, cfg.break_lengths_s, len(idx))

    # programmatic demand
    n_bids = rng.poisson(cfg.bids_per_break_mean, len(idx))
    total = int(n_bids.sum())
    adv = rng.integers(0, cfg.n_programmatic_advertisers, total)
    dur = _choice(rng, cfg.creative_durations_s, total)
    adv_rng = np.random.default_rng([cfg.seed, 0xAD])
    adv_mult = np.exp(cfg.advertiser_price_sigma * adv_rng.standard_normal(cfg.n_programmatic_advertisers))
    adv_cat = adv_rng.choice(len(CATEGORIES), cfg.n_programmatic_advertisers)
    cpa = None
    converted = np.zeros(total, dtype=bool)
    if cfg.price_source == "criteo":
        base = CriteoPrices(cfg.n_programmatic_advertisers, cfg.bid_cpm_median, cfg.seed).draw(adv, rng)
    elif cfg.price_source == "criteo-cpa":
        conv = CriteoConversions(cfg.n_programmatic_advertisers, cfg.bid_cpm_median, cfg.seed)
        cpa, p_hat, converted = conv.draw(adv, rng, cfg.rate_model, cfg.rate_inflation)
        base = 1000 * cpa * p_hat
    elif cfg.price_source == "lognormal":
        base = cfg.bid_cpm_median * np.exp(cfg.bid_cpm_sigma * rng.standard_normal(total)) * adv_mult[adv]
    else:
        raise ValueError(f"unknown price_source {cfg.price_source!r}")
    dev_mult = dict(cfg.device_price_multiplier)
    bid_dev = np.repeat(np.array([devices[v] for v in viewer.tolist()], dtype=object), n_bids)
    mult = np.array([dev_mult[d] for d in bid_dev])
    cpm = np.round(base * mult, 4)
    if cpa is not None:
        cpa = cpa * mult

    creatives: dict[tuple[int, int], Creative] = {}
    offsets = np.concatenate([[0], np.cumsum(n_bids)])
    breaks: list[Break] = []
    refused = 0
    for i in range(len(idx)):
        bid_id = f"{salt}-{i}"
        bids = []
        tt = int(title[i])
        for j in range(offsets[i], offsets[i + 1]):
            a, d = int(adv[j]), int(dur[j])
            if unsafe is not None and tt in unsafe[CATEGORIES[adv_cat[a]]]:
                refused += 1
                continue
            cr = creatives.get((a, d))
            if cr is None:
                cr = creatives[(a, d)] = Creative(f"p{a}-{d}", d)
            bids.append(Bid(f"{bid_id}:{j - offsets[i]}", f"p{a}", CATEGORIES[adv_cat[a]], cr, float(cpm[j]),
                            None if cpa is None else float(cpa[j]), bool(converted[j])))
        v = int(viewer[i])
        breaks.append(
            Break(bid_id, v, int(title[i]), titles.get(int(title[i]), frozenset()), devices[v],
                  int(t[i]), int(length[i]), tuple(bids))
        )
    breaks.sort(key=lambda b: (b.t, b.id))
    if stats is not None:
        stats["bids_total"] = stats.get("bids_total", 0) + total
        stats["bids_refused"] = stats.get("bids_refused", 0) + refused
    return breaks
