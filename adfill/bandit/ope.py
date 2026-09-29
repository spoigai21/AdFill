"""Off-policy evaluation on the Open Bandit Dataset (SPEC Phase 6).

Question: how would a policy we did not run have done? Here the answer is known. ZOZOTOWN ran a uniform
random policy and a Bernoulli Thompson-sampling (BTS) policy side by side in one A/B test, on the same
34 items and 3 positions, logging the true propensity of every action. So:

- ground truth: BTS's click rate, measured on its own log;
- estimate: BTS's click rate computed only from the random log, reweighted by propensities.

BTS here is context-free, so its action distribution for a given hour and position is estimated from
how often it actually showed each item then. Estimators: IPS, self-normalised IPS, the direct method
(a per item-and-position click model fitted on the random log) and doubly robust. The naive estimate
(the random log's own click rate) is the control: it answers a different question.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path("data/obd/open_bandit_dataset")
COLS = ["timestamp", "item_id", "position", "click", "propensity_score"]


def load(policy: str, campaign: str = "men", root: Path = ROOT) -> pd.DataFrame:
    df = pd.read_csv(root / policy / campaign / f"{campaign}.csv", usecols=COLS, engine="pyarrow")
    df["hour"] = pd.to_datetime(df.timestamp).dt.floor("h")
    return df


def action_distribution(bts: pd.DataFrame, n_items: int) -> pd.DataFrame:
    """P(item | hour, position) under BTS, as the share of BTS impressions in that cell showing the item."""
    counts = bts.groupby(["hour", "position", "item_id"]).size().unstack(fill_value=0)
    counts = counts.reindex(columns=range(n_items), fill_value=0)
    return counts.div(counts.sum(axis=1), axis=0)


def estimate(random_log: pd.DataFrame, pi_e: pd.DataFrame) -> dict:
    """Point estimates of BTS's click rate from the random log alone."""
    r = random_log[random_log.set_index(["hour", "position"]).index.isin(pi_e.index)]
    idx = pd.MultiIndex.from_arrays([r.hour, r.position])
    dist = pi_e.reindex(idx).to_numpy()  # (rows, items)
    items = r.item_id.to_numpy()
    y = r.click.to_numpy().astype(float)
    p_e = dist[np.arange(len(r)), items]
    w = p_e / r.propensity_score.to_numpy()

    q = r.groupby(["item_id", "position"]).click.mean()  # direct-method click model
    q_table = q.unstack(fill_value=r.click.mean()).reindex(range(dist.shape[1])).fillna(r.click.mean())
    q_rows = q_table.T.reindex(r.position.to_numpy()).to_numpy()  # (rows, items): q(item, row's position)
    q_logged = q_rows[np.arange(len(r)), items]
    dm_rows = (dist * q_rows).sum(axis=1)

    return {
        "rows_used": int(len(r)),
        "naive": float(y.mean()),
        "ips": float(np.mean(w * y)),
        "snips": float(np.sum(w * y) / np.sum(w)),
        "dm": float(dm_rows.mean()),
        "dr": float(np.mean(dm_rows + w * (y - q_logged))),
        "_rows": (w, y, dm_rows, q_logged),
    }


def bootstrap(rows, n: int, seed: int) -> dict:
    """95% intervals, resampling rows (the click model is held fixed)."""
    w, y, dm_rows, q_logged = rows
    rng = np.random.default_rng(seed)
    out = {k: [] for k in ("ips", "snips", "dr")}
    for _ in range(n):
        i = rng.integers(0, len(w), len(w))
        out["ips"].append(np.mean(w[i] * y[i]))
        out["snips"].append(np.sum(w[i] * y[i]) / np.sum(w[i]))
        out["dr"].append(np.mean(dm_rows[i] + w[i] * (y[i] - q_logged[i])))
    return {k: [float(np.quantile(v, 0.025)), float(np.quantile(v, 0.975))] for k, v in out.items()}


def run(campaign: str = "men", n_boot: int = 200, seed: int = 1) -> dict:
    rnd, bts = load("random", campaign), load("bts", campaign)
    n_items = int(max(rnd.item_id.max(), bts.item_id.max()) + 1)
    truth = float(bts.click.mean())
    est = estimate(rnd, action_distribution(bts, n_items))
    ci = bootstrap(est.pop("_rows"), n_boot, seed)
    return {
        "campaign": campaign, "items": n_items, "random_rows": int(len(rnd)), "bts_rows": int(len(bts)),
        "random_propensity": float(rnd.propensity_score.iloc[0]),
        "truth_bts_ctr": round(truth, 6),
        "estimates": {k: round(v, 6) for k, v in est.items() if k != "rows_used"},
        "relative_error": {k: round(abs(v - truth) / truth, 4) for k, v in est.items() if k != "rows_used"},
        "ci95": {k: [round(a, 6), round(b, 6)] for k, (a, b) in ci.items()},
        "truth_inside_ci95": {k: a <= truth <= b for k, (a, b) in ci.items()},
        "rows_used": est["rows_used"],
    }
