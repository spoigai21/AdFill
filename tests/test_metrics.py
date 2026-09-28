import numpy as np
import pytest

from adfill.predict.metrics import auc, calibration_ratio, expected_calibration_error, log_loss


def test_calibrated_model_scores_well_and_inflated_one_does_not():
    rng = np.random.default_rng(0)
    p = rng.uniform(0.01, 0.2, 200_000)
    y = (rng.random(len(p)) < p).astype(float)
    assert calibration_ratio(p, y) == pytest.approx(1.0, abs=0.02)
    assert expected_calibration_error(p, y) < 0.003
    assert calibration_ratio(p * 1.3, y) == pytest.approx(1.3, abs=0.03)
    assert expected_calibration_error(p * 1.3, y) > 0.02
    assert log_loss(p * 1.3, y) > log_loss(p, y)
    # Scaling does not change ranking: this is why AUC is reported last.
    assert auc(p * 1.3, y) == pytest.approx(auc(p, y))


def test_auc_extremes():
    y = np.array([0, 0, 1, 1])
    assert auc(np.array([0.1, 0.2, 0.3, 0.4]), y) == 1.0
    assert auc(np.array([0.4, 0.3, 0.2, 0.1]), y) == 0.0
