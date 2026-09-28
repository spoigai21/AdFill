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
    cfg = SimConfig(seed=args.seed, urgency_exponent=args.urgency_exponent, makegood_ratio=args.makegood_ratio,
                    price_source=args.price_source, bid_cpm_median=args.bid_cpm_median,
                    rate_model=args.rate_model, rate_inflation=args.rate_inflation)
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


def cmd_sweep(args: argparse.Namespace) -> None:
    from adfill.sweep import run_sweep

    out = run_sweep(args.name, args.windows, args.seeds, args.exponents, args.makegood_ratios, args.ml_dir,
                    args.run_dir, args.days, args.history_days, args.workers,
                    {"price_source": args.price_source, "bid_cpm_median": args.bid_cpm_median,
                     "rate_model": args.rate_model, "rate_inflation": args.rate_inflation})
    print(out.with_suffix(".md").read_text())


def cmd_prep_criteo(args: argparse.Namespace) -> None:
    from adfill.sim.prices import DEFAULT_CACHE, prepare_cache

    prepare_cache(Path(args.tsv))
    print(f"wrote {DEFAULT_CACHE}")


def cmd_pods(args: argparse.Namespace) -> None:
    from adfill.report.pods import pod_quality

    cfg = SimConfig(seed=args.seed)
    start = int(datetime.fromisoformat(args.start).replace(tzinfo=timezone.utc).timestamp())
    world = movielens_world(Path(args.ml_dir), cfg, start, args.days, args.history_days, 1.0)
    result = {"window": args.start, "seed": args.seed, "config": cfg.to_dict(), **pod_quality(world, cfg)}
    out = Path("results") / f"pods-{args.start}-s{args.seed}.json"
    out.write_text(json.dumps(result, indent=1) + "\n")
    print(json.dumps({k: v for k, v in result.items() if k != "config"}, indent=1))
    print(f"wrote {out}")


def cmd_train_models(args: argparse.Namespace) -> None:
    from adfill.predict.train import run

    print(json.dumps(run(seed=args.seed, train_rows=args.train_rows), indent=1))


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
    r.add_argument("--urgency-exponent", type=float, default=0.5)
    r.add_argument("--makegood-ratio", type=float, default=1.0)
    r.add_argument("--price-source", choices=["criteo", "criteo-cpa", "lognormal"], default="criteo")
    r.add_argument("--bid-cpm-median", type=float, default=18.0)
    r.add_argument("--rate-model", choices=["constant", "logistic_hashed", "gbm", "logistic_hashed_raw", "gbm_raw", "oracle"], default="gbm")
    r.add_argument("--rate-inflation", type=float, default=1.0)
    r.add_argument("--run-dir", default="data/runs")
    r.set_defaults(func=cmd_run)

    w = sub.add_parser("sweep", help="headline pair across MovieLens windows, seeds, curves and penalties")
    w.add_argument("--name", required=True)
    w.add_argument("--windows", nargs="+", default=["2016-03-01", "2016-09-01", "2017-03-01"])
    w.add_argument("--seeds", nargs="+", type=int, default=[1, 2, 3])
    w.add_argument("--exponents", nargs="+", type=float, default=[0.5, 1.0, 1.5, 2.0, 4.0])
    w.add_argument("--makegood-ratios", nargs="+", type=float, default=[0.5, 1.0, 2.0])
    w.add_argument("--ml-dir", default="data/ml-25m")
    w.add_argument("--days", type=int, default=30)
    w.add_argument("--history-days", type=int, default=14)
    w.add_argument("--workers", type=int, default=4)
    w.add_argument("--price-source", choices=["criteo", "criteo-cpa", "lognormal"], default="criteo")
    w.add_argument("--bid-cpm-median", type=float, default=18.0)
    w.add_argument("--rate-model", choices=["constant", "logistic_hashed", "gbm", "logistic_hashed_raw", "gbm_raw", "oracle"], default="gbm")
    w.add_argument("--rate-inflation", type=float, default=1.0)
    w.add_argument("--run-dir", default="data/runs")
    w.set_defaults(func=cmd_sweep)

    q = sub.add_parser("pods", help="greedy vs exact pod value, and per-decision cost by stage")
    q.add_argument("--start", default="2018-03-01")
    q.add_argument("--seed", type=int, default=1)
    q.add_argument("--days", type=int, default=30)
    q.add_argument("--history-days", type=int, default=14)
    q.add_argument("--ml-dir", default="data/ml-25m")
    q.set_defaults(func=cmd_pods)

    m = sub.add_parser("train-models", help="fit conversion-rate models on Criteo, time-forward split")
    m.add_argument("--seed", type=int, default=1)
    m.add_argument("--train-rows", type=int, default=4_000_000)
    m.set_defaults(func=cmd_train_models)

    c = sub.add_parser("prep-criteo", help="cache campaign and cost columns from the Criteo attribution TSV")
    c.add_argument("--tsv", default="data/criteo/criteo_attribution_dataset.tsv.gz")
    c.set_defaults(func=cmd_prep_criteo)
    args = p.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
