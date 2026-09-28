"""The request path (SPEC §7): eligibility -> caps -> price -> compare -> pod.

Holds delivery counters and ad-load state, but does no I/O; the caller records each Decision.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum

from adfill.core.caps import AdLoadTracker, FrequencyCaps
from adfill.core.eligibility import eligible
from adfill.core.model import Break, Campaign, Candidate, Kind
from adfill.core.pod import Pod, solve_exact
from adfill.core.urgency import UrgencyCurve, required_win_share
from adfill.forecast.base import SupplyForecast


class Policy(str, Enum):
    ADFILL = "adfill"
    GUARANTEED_FIRST = "guaranteed_first"
    HIGHEST_BID = "highest_bid"


# Guaranteed-first: any guaranteed ad outranks any bid, and among guaranteed ads the one furthest behind
# wins. Highest-bid: guaranteed ads only take slots no bid wants. Both are expressed as values so all
# three policies share one pod solver.
_GUARANTEED_FIRST_VALUE = 1e3
_HIGHEST_BID_LEFTOVER_VALUE = 1e-6
_PRIOR_N = 200


@dataclass(frozen=True)
class Decision:
    brk: Break
    length_s: int  # after the ad-load cap
    pod: Pod
    underfilled: bool  # no exact fit existed; the gap goes to house promos


class Engine:
    def __init__(
        self,
        policy: Policy,
        campaigns: list[Campaign],
        forecast: SupplyForecast,
        curve: UrgencyCurve = UrgencyCurve(),
        ad_load: AdLoadTracker | None = None,
        tolerance_s: int = 0,
        on_candidates: Callable[[Break, int, list[Candidate]], None] | None = None,
        new_viewer_prior: float = 0.5,
    ):
        self.policy = policy
        self.campaigns = campaigns
        self.forecast = forecast
        self.curve = curve
        self.ad_load = ad_load
        self.tolerance_s = tolerance_s
        self.delivered: dict[str, int] = {c.id: 0 for c in campaigns}  # progress toward goal
        self.impressions: dict[str, int] = {c.id: 0 for c in campaigns}
        self.reached: dict[str, set[int]] = {c.id: set() for c in campaigns if c.goal_type == "reach"}
        self.freq = FrequencyCaps()
        # Reach deals: of the matching breaks seen, how many came from viewers not yet reached. The
        # prior (pseudo-count _PRIOR_N) is the history's viewers-per-break ratio.
        self._new_seen = {cid: [_PRIOR_N * new_viewer_prior, float(_PRIOR_N)] for cid in self.reached}
        self.on_candidates = on_candidates  # instrumentation hook; must not mutate its arguments
        # Cumulative wall time per request-path stage (SPEC §7), for the per-decision cost breakdown.
        self.stage_s = {"forecast_and_caps": 0.0, "eligibility_and_pricing": 0.0, "pod": 0.0, "record": 0.0}

    def new_viewer_share(self, campaign_id: str) -> float:
        new, seen = self._new_seen[campaign_id]
        return new / seen

    def guaranteed_value(self, campaign: Campaign, now: int) -> float:
        if self.policy is Policy.HIGHEST_BID:
            return _HIGHEST_BID_LEFTOVER_VALUE
        debt = campaign.goal - self.delivered[campaign.id]
        supply = self.forecast.matching_supply(campaign, now)
        if campaign.goal_type == "reach":
            supply *= self.new_viewer_share(campaign.id)  # only unreached viewers pay down a reach goal
        share = required_win_share(debt, supply)
        if self.policy is Policy.GUARANTEED_FIRST:
            return _GUARANTEED_FIRST_VALUE + min(share, 10.0)
        return campaign.skip_cost_per_imp * self.curve(share)

    def candidates(self, brk: Break) -> list[Candidate]:
        out: list[Candidate] = []
        for c in self.campaigns:
            if self.delivered[c.id] >= c.goal or not eligible(c, brk):
                continue
            if c.goal_type == "reach":
                fresh = brk.viewer not in self.reached[c.id]
                stat = self._new_seen[c.id]
                stat[0] += fresh
                stat[1] += 1
                if not fresh:
                    continue
            if not self.freq.allowed(c.id, c.freq_cap, c.freq_window_s, brk.viewer, brk.t):
                continue
            value = self.guaranteed_value(c, brk.t)
            for cr in c.creatives:
                out.append(
                    Candidate(Kind.GUARANTEED, c.id, c.advertiser, c.category, cr.duration_s, value, c.cpm)
                )
        for b in brk.bids:
            out.append(
                Candidate(
                    Kind.PROGRAMMATIC, b.id, b.advertiser, b.category, b.creative.duration_s, b.cpm / 1000, b.cpm,
                    b.paid,
                )
            )
        return out

    def decide(self, brk: Break) -> Decision:
        t0 = time.perf_counter()
        self.forecast.observe(brk)
        length = brk.length_s
        if self.ad_load is not None:
            length = min(length, self.ad_load.remaining(brk.viewer, brk.t))
        t1 = time.perf_counter()
        cands = self.candidates(brk)
        t2 = time.perf_counter()
        if self.on_candidates is not None:
            self.on_candidates(brk, length, cands)
            t2 = time.perf_counter()
        pod = solve_exact(cands, length, self.tolerance_s)
        underfilled = pod is None
        if pod is None:
            pod = solve_exact(cands, length, tolerance=length)
        t3 = time.perf_counter()
        for item in pod.items:
            if item.kind is Kind.GUARANTEED:
                cid = item.ref
                self.impressions[cid] += 1
                self.freq.record(cid, brk.viewer, brk.t)
                if cid in self.reached:
                    self.reached[cid].add(brk.viewer)
                    self.delivered[cid] = len(self.reached[cid])
                else:
                    self.delivered[cid] += 1
        if self.ad_load is not None:
            self.ad_load.record(brk.viewer, brk.t, pod.duration_s)
        t4 = time.perf_counter()
        st = self.stage_s
        st["forecast_and_caps"] += t1 - t0
        st["eligibility_and_pricing"] += t2 - t1
        st["pod"] += t3 - t2
        st["record"] += t4 - t3
        return Decision(brk, length, pod, underfilled)
