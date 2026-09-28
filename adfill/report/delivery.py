"""Second pass over a decision log: delivery, revenue, makegoods. Nothing here trusts engine state."""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path

from adfill.core.model import Campaign


@dataclass(frozen=True)
class Headline:
    breaks: int
    programmatic_revenue: float
    guaranteed_revenue: float
    makegood_liability: float
    total_revenue: float  # programmatic + guaranteed - makegoods
    campaigns: int
    delivered_in_full: int
    delivered_in_full_share: float
    mean_delivery_share: float  # mean of min(1, delivered / goal)
    ad_seconds_requested: int
    ad_seconds_filled: int
    underfilled_breaks: int

    def to_dict(self) -> dict:
        return asdict(self)


def read_delivery(log_path: Path) -> tuple[Counter, dict]:
    """Per campaign: impressions served; totals; and (in totals["viewers"]) the viewers each reached."""
    delivered: Counter = Counter()
    viewers: dict[str, set[int]] = defaultdict(set)
    totals = {"breaks": 0, "prog": 0.0, "requested": 0, "filled": 0, "underfilled": 0}
    with log_path.open() as f:
        for line in f:
            row = json.loads(line)
            totals["breaks"] += 1
            totals["requested"] += row["requested_s"]
            totals["filled"] += row["filled_s"]
            totals["underfilled"] += row["underfilled"]
            for ad in row["ads"]:
                if ad["kind"] == "guaranteed":
                    delivered[ad["ref"]] += 1
                    viewers[ad["ref"]].add(row["viewer"])
                else:
                    totals["prog"] += ad["paid"]
    totals["viewers"] = viewers
    return delivered, totals


def headline(log_path: Path, campaigns: list[Campaign]) -> tuple[Headline, Counter]:
    impressions, totals = read_delivery(log_path)
    # Progress toward goal: impressions, or unique viewers for reach deals.
    delivered = Counter({c.id: len(totals["viewers"][c.id]) if c.goal_type == "reach" else impressions[c.id]
                         for c in campaigns})
    guaranteed = makegood = 0.0
    full = 0
    shares = []
    for c in campaigns:
        got = delivered[c.id]
        billed = min(got, c.goal)
        shortfall = c.goal - billed
        guaranteed += billed * c.cpm / 1000
        makegood += shortfall * c.makegood_cpm / 1000
        full += shortfall == 0
        shares.append(billed / c.goal)
    n = len(campaigns)
    h = Headline(
        breaks=totals["breaks"],
        programmatic_revenue=round(totals["prog"], 2),
        guaranteed_revenue=round(guaranteed, 2),
        makegood_liability=round(makegood, 2),
        total_revenue=round(totals["prog"] + guaranteed - makegood, 2),
        campaigns=n,
        delivered_in_full=full,
        delivered_in_full_share=round(full / n, 4) if n else 0.0,
        mean_delivery_share=round(sum(shares) / n, 4) if n else 0.0,
        ad_seconds_requested=totals["requested"],
        ad_seconds_filled=totals["filled"],
        underfilled_breaks=totals["underfilled"],
    )
    return h, delivered
