"""Every synthesized quantity, in one place. Each field has a matching line in spec/ASSUMPTIONS.md."""

from __future__ import annotations

from dataclasses import asdict, dataclass

CATEGORIES = (
    "auto", "beverage", "fast_food", "telecom", "retail",
    "finance", "pharma", "travel", "tech", "cpg",
)
DEVICES = ("tv", "mobile", "desktop", "tablet")


@dataclass(frozen=True)
class SimConfig:
    seed: int = 1

    # sessions (MovieLens source)
    max_sessions_per_viewer_day: int = 3

    # breaks
    breaks_per_session: tuple[tuple[int, float], ...] = ((1, 0.30), (2, 0.35), (3, 0.25), (4, 0.10))
    break_lengths_s: tuple[tuple[int, float], ...] = ((30, 0.20), (60, 0.40), (90, 0.25), (120, 0.15))
    break_spacing_s: int = 15 * 60
    device_mix: tuple[tuple[str, float], ...] = (("tv", 0.55), ("mobile", 0.20), ("desktop", 0.15), ("tablet", 0.10))
    max_ad_seconds_per_hour: int = 240

    # programmatic demand
    price_source: str = "criteo"  # "criteo" (real clearing prices) or "lognormal" (no data needed)
    n_programmatic_advertisers: int = 60
    bids_per_break_mean: float = 4.0
    bid_cpm_median: float = 18.0
    bid_cpm_sigma: float = 0.7
    advertiser_price_sigma: float = 0.3
    device_price_multiplier: tuple[tuple[str, float], ...] = (
        ("tv", 1.3), ("mobile", 0.8), ("desktop", 0.9), ("tablet", 0.9),
    )
    creative_durations_s: tuple[tuple[int, float], ...] = ((15, 0.5), (30, 0.5))

    # guaranteed deals
    n_campaigns: int = 40
    campaign_cpm_range: tuple[float, float] = (30.0, 50.0)
    makegood_ratio: float = 1.0  # makegood_cpm = makegood_ratio * cpm
    flight_days_range: tuple[int, int] = (14, 45)
    sell_through_range: tuple[float, float] = (0.05, 0.7)  # relative weight of each deal before scaling
    guaranteed_book_share: float = 0.4  # share of all forecast ad slots sold as guaranteed
    genre_targeted_share: float = 0.7
    genres_per_campaign_range: tuple[int, int] = (1, 3)
    device_targeted_share: float = 0.4  # targeted campaigns buy TV only

    # allocation
    urgency_exponent: float = 0.5  # chosen on tuning windows only; see spec/BUG_LOG.md B6
    pod_tolerance_s: int = 0

    def to_dict(self) -> dict:
        return asdict(self)
