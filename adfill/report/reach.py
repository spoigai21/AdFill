"""Reach and frequency per campaign (SPEC §8), from a decision log, plus cap-violation checks."""

from __future__ import annotations

import json
from collections import Counter, defaultdict, deque
from pathlib import Path

from adfill.core.model import Campaign

FREQ_BUCKETS = ((1, 1), (2, 2), (3, 3), (4, 5), (6, 10), (11, 10**9))


def _bucket(n: int) -> str:
    for lo, hi in FREQ_BUCKETS:
        if n <= hi:
            return str(lo) if lo == hi else (f"{lo}-{hi}" if hi < 10**9 else f"{lo}+")
    raise AssertionError


def exposures(log_path: Path) -> dict[str, list[tuple[int, int]]]:
    """Per campaign: (t, viewer) of every guaranteed ad served, in log order."""
    out: dict[str, list[tuple[int, int]]] = defaultdict(list)
    with log_path.open() as f:
        for line in f:
            row = json.loads(line)
            for ad in row["ads"]:
                if ad["kind"] == "guaranteed":
                    out[ad["ref"]].append((row["t"], row["viewer"]))
    return out


def cap_violations(events: list[tuple[int, int]], cap: int, window_s: int) -> int:
    """Exposures that exceed `cap` for their viewer within any trailing window. Events in time order."""
    if cap <= 0:
        return 0
    seen: dict[int, deque[int]] = defaultdict(deque)
    bad = 0
    for t, v in events:
        q = seen[v]
        while q and q[0] <= t - window_s:
            q.popleft()
        q.append(t)
        bad += len(q) > cap
    return bad


def reach_report(log_path: Path, campaigns: list[Campaign], cap: int = 0, window_s: int = 86_400) -> dict:
    """`cap` checks every campaign against one cap, whether or not it was enforced (to show what it would
    have cut); each campaign's own cap is checked too."""
    ex = exposures(log_path)
    rows, hist = [], Counter()
    total_imps = over3 = 0
    violations = own_violations = 0
    for c in campaigns:
        ev = ex.get(c.id, [])
        per_viewer = Counter(v for _, v in ev)
        for n in per_viewer.values():
            hist[_bucket(n)] += n  # impressions, not viewers, in each frequency bucket
        total_imps += len(ev)
        over3 += sum(n - 3 for n in per_viewer.values() if n > 3)
        violations += cap_violations(ev, cap, window_s)
        own_violations += cap_violations(ev, c.freq_cap, c.freq_window_s)
        rows.append({"campaign": c.id, "goal_type": c.goal_type, "goal": c.goal, "impressions": len(ev),
                     "reach": len(per_viewer),
                     "avg_frequency": round(len(ev) / len(per_viewer), 3) if per_viewer else 0.0,
                     "max_frequency": max(per_viewer.values(), default=0)})
    order = [_bucket(lo) for lo, _ in FREQ_BUCKETS]
    return {
        "impressions": total_imps,
        "reach": sum(r["reach"] for r in rows),
        "avg_frequency": round(total_imps / max(1, sum(r["reach"] for r in rows)), 3),
        "impressions_beyond_3rd_per_viewer_share": round(over3 / max(1, total_imps), 4),
        "impression_share_by_frequency": {b: round(hist[b] / max(1, total_imps), 4) for b in order},
        "violations_of_reference_cap": violations,
        "violations_of_own_caps": own_violations,
        "campaigns": rows,
    }
