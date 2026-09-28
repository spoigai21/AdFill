"""Calibration first, ranking last (SPEC §2.3): the predicted rate is multiplied into the value."""

from __future__ import annotations

import numpy as np


def calibration_ratio(p: np.ndarray, y: np.ndarray) -> float:
    """Mean predicted over mean observed. 1.0 is calibrated in aggregate; 1.3 inflates every value 30%."""
    return float(np.mean(p) / np.mean(y))


def expected_calibration_error(p: np.ndarray, y: np.ndarray, bins: int = 20) -> float:
    """Equal-mass bins; weighted mean of |mean predicted - mean observed| per bin."""
    order = np.argsort(p, kind="stable")
    err = 0.0
    for chunk in np.array_split(order, bins):
        if len(chunk):
            err += len(chunk) * abs(p[chunk].mean() - y[chunk].mean())
    return float(err / len(p))


def log_loss(p: np.ndarray, y: np.ndarray) -> float:
    p = np.clip(p, 1e-7, 1 - 1e-7)
    return float(-np.mean(y * np.log(p) + (1 - y) * np.log(1 - p)))


def auc(p: np.ndarray, y: np.ndarray) -> float:
    """Rank-based AUC with ties averaged."""
    from scipy.stats import rankdata

    r = rankdata(p)
    n1 = y.sum()
    n0 = len(y) - n1
    return float((r[y == 1].sum() - n1 * (n1 + 1) / 2) / (n1 * n0))


def report(p: np.ndarray, y: np.ndarray) -> dict:
    return {
        "calibration_ratio": round(calibration_ratio(p, y), 4),
        "ece": round(expected_calibration_error(p, y), 5),
        "log_loss": round(log_loss(p, y), 5),
        "auc": round(auc(p, y), 4),
    }
