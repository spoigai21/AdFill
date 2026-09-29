import argparse
import json

import pytest

from adfill import cli
from adfill.report.guarantee import summarize


def _args(**kw):
    base = dict(preset=None, exponents=None)
    base.update(kw)
    return argparse.Namespace(**base)


def test_no_preset_keeps_published_defaults(monkeypatch):
    monkeypatch.setattr(cli.sys, "argv", ["adfill", "sweep"])
    config, exps = cli._apply_preset(_args(), {"price_source": "criteo"})
    assert config == {"price_source": "criteo"} and exps == [0.5, 1.0, 1.5, 2.0, 4.0]


def test_preset_fills_unset_values_and_explicit_flags_win(monkeypatch):
    monkeypatch.setattr(cli.sys, "argv", ["adfill", "sweep", "--preset", "recommended", "--freq-cap", "3"])
    config, exps = cli._apply_preset(_args(preset="recommended"), {"price_source": "criteo", "freq_cap": 3,
                                                                  "forecast_contention": False})
    assert config["price_source"] == "criteo-cpa" and config["forecast_contention"] is True
    assert config["freq_cap"] == 3  # explicit
    assert exps == [2.0] and config["urgency_exponent"] == 2.0


def test_guarantee_summary(tmp_path):
    def row(policy, prog, imps, shares, exponent=None):
        return {"policy": policy, "exponent": exponent, "makegood_ratio": 1.0, "window": "w", "seed": 1,
                "programmatic_revenue": prog, "guaranteed_revenue": imps * 0.04, "guaranteed_impressions": imps,
                "delivery_share_of_goal": shares, "campaigns_over_goal": 0}
    rows = [row("highest_bid", 100.0, 1000, [0.2, 0.5]), row("guaranteed_first", 40.0, 3000, [1.0, 1.0]),
            row("adfill", 90.0, 3000, [1.0, 0.95], exponent=0.5)]
    path = tmp_path / "r.json"
    path.write_text(json.dumps({"rows": rows}))
    s = summarize(path, 0.5)
    assert s["adfill"]["cash_forgone_vs_highest_bid"] == pytest.approx(10.0)
    assert s["adfill"]["cash_forgone_per_extra_1000_guaranteed"] == pytest.approx(5.0)   # $10 over 2,000 extra
    assert s["guaranteed_first"]["cash_forgone_per_extra_1000_guaranteed"] == pytest.approx(30.0)
    assert s["adfill"]["delivery_share"]["below_99pct"] == 1
    assert s["highest_bid"]["cash_forgone_per_extra_1000_guaranteed"] is None
