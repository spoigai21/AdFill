"""Cost of a guarantee and the delivery distribution (SPEC §8), from a sweep's result file.

Cost of a guarantee: the programmatic cash a policy gives up to keep its promises, measured against
highest-bid (which ignores them), per 1,000 guaranteed impressions delivered. Set beside it: the contract
price those impressions earn. A policy that keeps promises by giving up cheap slots pays less per
guaranteed impression than one that gives up the best slots.

Delivery distribution: each campaign's delivery as a share of its goal, pooled over worlds.
"""

from __future__ import annotations

import json
from pathlib import Path
from statistics import median


def summarize(result_path: Path, exponent: float | None = None, makegood_ratio: float = 1.0) -> dict:
    rows = json.loads(result_path.read_text())["rows"]
    rows = [r for r in rows if r["makegood_ratio"] == makegood_ratio]

    def pick(policy):
        out = [r for r in rows if r["policy"] == policy and (policy != "adfill" or exponent is None
                                                              or r["exponent"] == exponent)]
        return sorted(out, key=lambda r: (r["window"], r["seed"]))

    hb = pick("highest_bid")
    hb_imps = sum(r["guaranteed_impressions"] for r in hb)
    out = {}
    for policy in ("guaranteed_first", "highest_bid", "adfill"):
        rs = pick(policy)
        if not rs or "guaranteed_impressions" not in rs[0]:
            raise ValueError(f"{result_path} lacks per-campaign delivery fields; rerun the sweep")
        forgone = sum(h["programmatic_revenue"] - r["programmatic_revenue"] for r, h in zip(rs, hb))
        imps = sum(r["guaranteed_impressions"] for r in rs)
        shares = [x for r in rs for x in r["delivery_share_of_goal"]]
        out[policy] = {
            "programmatic_revenue": round(sum(r["programmatic_revenue"] for r in rs), 2),
            "guaranteed_revenue": round(sum(r["guaranteed_revenue"] for r in rs), 2),
            "guaranteed_impressions": imps,
            "cash_forgone_vs_highest_bid": round(forgone, 2),
            "cash_forgone_per_1000_guaranteed": round(1000 * forgone / imps, 2) if imps else None,
            # Highest-bid delivers some guarantees anyway from slots no bid wanted; this prices only the rest.
            "cash_forgone_per_extra_1000_guaranteed": round(1000 * forgone / (imps - hb_imps), 2)
            if imps > hb_imps else None,
            "contract_revenue_per_1000_guaranteed": round(
                1000 * sum(r["guaranteed_revenue"] for r in rs) / imps, 2) if imps else None,
            "delivery_share": {"campaigns": len(shares), "min": round(min(shares), 4),
                               "p10": round(sorted(shares)[len(shares) // 10], 4),
                               "median": round(median(shares), 4),
                               "below_90pct": sum(x < 0.9 for x in shares),
                               "below_99pct": sum(x < 0.99 for x in shares)},
            "campaigns_over_goal": sum(r["campaigns_over_goal"] for r in rs),
        }
    return out
