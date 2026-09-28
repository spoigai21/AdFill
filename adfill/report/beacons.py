"""Delivery reports as a real pipeline sees them: duplicated and out of order (SPEC §8, Phase 4).

Every served ad emits an impression beacon with a unique id (break id + slot). Beacons are duplicated
with probability `dup_rate` and arrive after a random delay, so they are processed out of order. Billing
must dedupe by id; caps and the ad-load limit are checked on serve time, not arrival time.
The naive counter (no dedupe, arrival order) is kept as a negative control.
"""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

from adfill.report.reach import cap_violations


def beacon_stream(log_path: Path, dup_rate: float, max_delay_s: int, seed: int) -> list[dict]:
    rng = np.random.default_rng([seed, 0xBEAC])
    events = []
    with log_path.open() as f:
        for line in f:
            row = json.loads(line)
            for slot, ad in enumerate(row["ads"]):
                base = {"id": f"{row['break']}#{slot}", "kind": ad["kind"], "ref": ad["ref"],
                        "viewer": row["viewer"], "served": row["t"], "seconds": ad["duration_s"]}
                copies = 1 + int(rng.random() < dup_rate)
                for _ in range(copies):
                    events.append({**base, "arrived": row["t"] + int(rng.integers(0, max_delay_s + 1))})
    events.sort(key=lambda e: (e["arrived"], e["id"]))
    return events


def reconcile(events: list[dict], dedupe: bool) -> dict:
    """Counts per campaign, per-viewer exposures in serve order, and ad seconds per viewer."""
    seen: set[str] = set()
    kept = []
    for e in events:
        if dedupe:
            if e["id"] in seen:
                continue
            seen.add(e["id"])
        kept.append(e)
    if dedupe:
        kept.sort(key=lambda e: (e["served"], e["id"]))  # checks run on serve time, not arrival time
    counts = Counter(e["ref"] for e in kept if e["kind"] == "guaranteed")
    exposures = defaultdict(list)
    ad_seconds = defaultdict(list)
    for e in kept:
        if e["kind"] == "guaranteed":
            exposures[e["ref"]].append((e["served"], e["viewer"]))
        ad_seconds[e["viewer"]].append((e["served"], e["seconds"]))
    return {"counts": counts, "exposures": exposures, "ad_seconds": ad_seconds, "events": len(kept)}


def ad_load_violations(ad_seconds: dict[int, list[tuple[int, int]]], max_seconds: int, window_s: int = 3600) -> int:
    """Viewers whose ad seconds, as reported, exceed the cap in some trailing window."""
    bad = 0
    for items in ad_seconds.values():
        items = sorted(items)
        lo, total = 0, 0
        for hi in range(len(items)):
            total += items[hi][1]
            while items[lo][0] <= items[hi][0] - window_s:
                total -= items[lo][1]
                lo += 1
            if total > max_seconds:
                bad += 1
                break
    return bad


def audit(log_path: Path, caps: dict[str, tuple[int, int]], max_ad_seconds: int, dup_rate: float,
          max_delay_s: int, seed: int) -> dict:
    """Compare reconciled and naive counting against the decision log's ground truth."""
    truth = reconcile(beacon_stream(log_path, 0.0, 0, seed), dedupe=True)
    stream = beacon_stream(log_path, dup_rate, max_delay_s, seed)
    out = {"beacons": len(stream), "true_impressions": truth["events"]}
    for name, dedupe in (("reconciled", True), ("naive", False)):
        r = reconcile(stream, dedupe)
        cap_bad = sum(cap_violations(sorted(r["exposures"][cid]) if dedupe else r["exposures"][cid], cap, w)
                      for cid, (cap, w) in caps.items())
        out[name] = {
            "impressions_counted": r["events"],
            "overcount": round(r["events"] / truth["events"] - 1, 4),
            "campaigns_miscounted": sum(r["counts"][c] != truth["counts"][c] for c in truth["counts"]),
            "frequency_cap_violations": cap_bad,
            "viewers_over_ad_load": ad_load_violations(r["ad_seconds"], max_ad_seconds),
        }
    return out
