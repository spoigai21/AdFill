"""adfill run: build a world, run all three policies over it, print and save the headline pair."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from adfill.core.engine import Policy
from adfill.report.delivery import headline
from adfill.sim.config import SimConfig
from adfill.sim.runner import run_policy
from adfill.sim.world import movielens_world, synthetic_world


def _campaign_rows(campaigns) -> list[dict]:
    return [
        {"id": c.id, "category": c.category, "goal": c.goal, "start": c.start, "end": c.end,
         "genres": sorted(c.targeting.genres) if c.targeting.genres else None,
         "devices": sorted(c.targeting.devices) if c.targeting.devices else None,
         "cpm": c.cpm, "makegood_cpm": c.makegood_cpm,
         "durations_s": [cr.duration_s for cr in c.creatives]}
        for c in campaigns
    ]


def cmd_run(args: argparse.Namespace) -> None:
    cfg = SimConfig(seed=args.seed, urgency_exponent=args.urgency_exponent, makegood_ratio=args.makegood_ratio)
    if args.source == "movielens":
        start = int(datetime.fromisoformat(args.start).replace(tzinfo=timezone.utc).timestamp())
        world = movielens_world(Path(args.ml_dir), cfg, start, args.days, args.history_days, args.viewer_fraction)
    else:
        world = synthetic_world(cfg, window_days=args.days, history_days=args.history_days)

    run_dir = Path(args.run_dir) / args.name
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "campaigns.json").write_text(json.dumps(_campaign_rows(world.campaigns), indent=1))
    print(f"{len(world.breaks):,} breaks, {len(world.campaigns)} campaigns, "
          f"{sum(c.goal for c in world.campaigns):,} guaranteed impressions promised")

    results = {}
    print(f"\n{'policy':<18}{'total revenue':>15}{'makegoods':>12}{'delivered in full':>20}{'µs/decision':>13}")
    for policy in Policy:
        _, us = run_policy(world, policy, cfg, run_dir / f"{policy.value}.jsonl")
        h, _ = headline(run_dir / f"{policy.value}.jsonl", world.campaigns)
        results[policy.value] = {**h.to_dict(), "us_per_decision": round(us, 1)}
        print(f"{policy.value:<18}{h.total_revenue:>15,.2f}{h.makegood_liability:>12,.2f}"
              f"{f'{h.delivered_in_full}/{h.campaigns}':>20}{us:>13.0f}")

    out = Path("results") / f"{args.name}.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps({"args": {k: v for k, v in vars(args).items() if k != "func"}, "config": cfg.to_dict(), "results": results}, indent=1) + "\n")
    print(f"\nwrote {out}")


def main() -> None:
    p = argparse.ArgumentParser(prog="adfill")
    sub = p.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run", help="run all three policies over one simulated world")
    r.add_argument("--name", required=True)
    r.add_argument("--source", choices=["synthetic", "movielens"], default="synthetic")
    r.add_argument("--seed", type=int, default=1)
    r.add_argument("--ml-dir", default="data/ml-25m")
    r.add_argument("--start", default="2016-03-01")
    r.add_argument("--days", type=int, default=30)
    r.add_argument("--history-days", type=int, default=14)
    r.add_argument("--viewer-fraction", type=float, default=0.1)
    r.add_argument("--urgency-exponent", type=float, default=1.0)
    r.add_argument("--makegood-ratio", type=float, default=1.0)
    r.add_argument("--run-dir", default="data/runs")
    r.set_defaults(func=cmd_run)
    args = p.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
