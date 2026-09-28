"""Conversion-rate models on Criteo, split forward in time (SPEC §2.3).

Days 0-19 train, 20-23 validate (isotonic calibration only), 24-30 test. The simulation draws its
programmatic impressions from the test days, so no model has seen a row it is later scored on.

Features are only what is known before the impression is shown: campaign, the nine anonymised
categoricals, time since the user's last click, hour of day, and how many impressions the user has had
so far. Excluded as leaks: cost and click (known only after the impression), and conversion_timestamp,
conversion_id, attribution, click_pos, click_nb and cpo (all derived from the outcome).
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.feature_extraction import FeatureHasher
from sklearn.isotonic import IsotonicRegression
from sklearn.linear_model import SGDClassifier

from adfill.predict.metrics import report

FULL = Path("data/criteo/full.parquet")
SCORED = Path("data/criteo/scored_test.parquet")
TRAIN, VALID, TEST = (0, 20), (20, 24), (24, 31)
CATS = [f"cat{i}" for i in range(1, 10)]
MAX_CODES = 254  # HistGradientBoosting allows at most 255 categories per feature; the last is "other"
PRIOR_STRENGTH = 200  # pseudo-impressions shrinking a campaign's rate toward the global rate


def load(path: Path = FULL) -> pd.DataFrame:
    df = pd.read_parquet(path, columns=["timestamp", "uid", "campaign", "conversion", "time_since_last_click", *CATS])
    df = df.sort_values(["timestamp", "uid"], kind="stable").reset_index(drop=True)
    df["day"] = (df.timestamp // 86_400).astype("int16")
    df["hour"] = ((df.timestamp // 3600) % 24).astype("int8")
    df["prior_imps"] = df.groupby("uid").cumcount().astype("int32")  # causal: counts earlier rows only
    df["tslc"] = df.time_since_last_click.where(df.time_since_last_click >= 0).astype("float32")
    return df


def split(df: pd.DataFrame, days: tuple[int, int]) -> pd.DataFrame:
    return df[(df.day >= days[0]) & (df.day < days[1])]


def campaign_rates(train: pd.DataFrame) -> pd.Series:
    g = train.groupby("campaign").conversion.agg(["sum", "count"])
    base = train.conversion.mean()
    return (g["sum"] + PRIOR_STRENGTH * base) / (g["count"] + PRIOR_STRENGTH)


# --- hashed logistic regression ------------------------------------------------------------------

def _bucket(x: np.ndarray, cap: int) -> np.ndarray:
    return np.minimum(np.floor(np.log2(np.nan_to_num(x, nan=-1) + 2)), cap).astype(int)


def _hashed(df: pd.DataFrame, hasher: FeatureHasher):
    tslc_b = np.where(df.tslc.isna(), -1, _bucket(df.tslc.to_numpy(), 20))
    cols = {c: df[c].to_numpy() for c in ["campaign", *CATS]}
    cols["tslc_b"] = tslc_b
    cols["hour"] = df.hour.to_numpy()
    cols["prior_b"] = _bucket(df.prior_imps.to_numpy(), 12)
    cols["camp_x_tslc"] = df.campaign.to_numpy().astype(np.int64) * 100 + tslc_b
    rows = ([f"{k}={v[i]}" for k, v in cols.items()] for i in range(len(df)))
    return hasher.transform(rows)


def train_lr(train: pd.DataFrame, seed: int):
    hasher = FeatureHasher(n_features=2**20, input_type="string", alternate_sign=False)
    model = SGDClassifier(loss="log_loss", alpha=1e-6, learning_rate="adaptive", eta0=0.02, random_state=seed)
    rng = np.random.default_rng(seed)
    for _ in range(2):  # epochs
        for idx in np.array_split(rng.permutation(len(train)), max(1, len(train) // 500_000)):
            chunk = train.iloc[np.sort(idx)]
            model.partial_fit(_hashed(chunk, hasher), chunk.conversion.to_numpy(), classes=[0, 1])
    return lambda d: model.predict_proba(_hashed(d, hasher))[:, 1]


# --- gradient-boosted trees ----------------------------------------------------------------------

def _codebook(train: pd.DataFrame) -> dict[str, dict]:
    return {c: {v: i for i, v in enumerate(train[c].value_counts().index[:MAX_CODES])} for c in ["campaign", *CATS]}


def _dense(df: pd.DataFrame, codes: dict[str, dict], rates: pd.Series, base: float) -> np.ndarray:
    cat = [df[c].map(codes[c]).fillna(MAX_CODES).to_numpy(np.float32) for c in ["campaign", *CATS]]
    num = [
        df.campaign.map(rates).fillna(base).to_numpy(np.float32),
        df.tslc.to_numpy(np.float32),
        df.hour.to_numpy(np.float32),
        np.log1p(df.prior_imps.to_numpy(np.float32)),
    ]
    return np.column_stack(cat + num)


def train_gbm(train: pd.DataFrame, rates: pd.Series, seed: int):
    codes, base = _codebook(train), float(train.conversion.mean())
    n_cat = 1 + len(CATS)
    model = HistGradientBoostingClassifier(
        max_iter=300, learning_rate=0.1, max_leaf_nodes=63, min_samples_leaf=200, l2_regularization=1.0,
        categorical_features=list(range(n_cat)), early_stopping=False, random_state=seed,
    )
    model.fit(_dense(train, codes, rates, base), train.conversion.to_numpy())
    return lambda d: model.predict_proba(_dense(d, codes, rates, base))[:, 1]


# --- pipeline ------------------------------------------------------------------------------------

def run(seed: int = 1, train_rows: int = 4_000_000, out_metrics: Path = Path("results/predict-metrics.json")) -> dict:
    t0 = time.time()
    df = load()
    train_all, valid, test = split(df, TRAIN), split(df, VALID), split(df, TEST)
    train = train_all.sample(n=min(train_rows, len(train_all)), random_state=seed).sort_index()
    rates = campaign_rates(train_all)
    base = float(train_all.conversion.mean())

    predictors = {
        "constant": lambda d: d.campaign.map(rates).fillna(base).to_numpy(),
        "logistic_hashed": train_lr(train, seed),
        "gbm": train_gbm(train, rates, seed),
    }
    y_valid, y_test = valid.conversion.to_numpy(), test.conversion.to_numpy()
    metrics: dict = {"split_days": {"train": TRAIN, "valid": VALID, "test": TEST},
                     "rows": {"train_used": len(train), "train_period": len(train_all), "valid": len(valid),
                              "test": len(test)},
                     "test_base_rate": round(float(y_test.mean()), 5), "models": {}}
    scored = pd.DataFrame({"campaign": test.campaign.to_numpy(), "day": test.day.to_numpy(),
                           "conversion": y_test.astype("int8")})
    for name, predict in predictors.items():
        raw_valid, raw_test = predict(valid), predict(test)
        iso = IsotonicRegression(out_of_bounds="clip", y_min=1e-6, y_max=1 - 1e-6).fit(raw_valid, y_valid)
        cal_test = iso.predict(raw_test)
        metrics["models"][name] = {"raw": report(raw_test, y_test), "calibrated": report(cal_test, y_test)}
        scored[f"p_{name}"] = cal_test.astype("float32")
        scored[f"p_{name}_raw"] = np.clip(raw_test, 0, 1).astype("float32")
    SCORED.parent.mkdir(parents=True, exist_ok=True)
    scored.to_parquet(SCORED, index=False)
    metrics["seconds"] = round(time.time() - t0)
    out_metrics.parent.mkdir(exist_ok=True)
    out_metrics.write_text(json.dumps(metrics, indent=1) + "\n")
    return metrics
