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
         "brief": c.targeting.brief, "blocked_titles": len(c.targeting.blocked),
         "devices": sorted(c.targeting.devices) if c.targeting.devices else None,
         "cpm": c.cpm, "makegood_cpm": c.makegood_cpm,
         "durations_s": [cr.duration_s for cr in c.creatives]}
        for c in campaigns
    ]


def cmd_run(args: argparse.Namespace) -> None:
    cfg = SimConfig(seed=args.seed, urgency_exponent=args.urgency_exponent, makegood_ratio=args.makegood_ratio,
                    price_source=args.price_source, bid_cpm_median=args.bid_cpm_median,
                    rate_model=args.rate_model, rate_inflation=args.rate_inflation,
                    targeting_mode=args.targeting_mode, brand_safety=args.brand_safety)
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
                     "rate_model": args.rate_model, "rate_inflation": args.rate_inflation,
                     "targeting_mode": args.targeting_mode, "brand_safety": args.brand_safety,
                     "guaranteed_book_share": args.book_share, "forecast_model": args.forecast_model,
                     "forecast_contention": args.contention, "forecast_bias": args.forecast_bias,
                     "avails_check": args.avails, "avails_margin": args.avails_margin,
                     "booking_forecast_bias": args.booking_bias, "reach_share": args.reach_share,
                     "freq_cap": args.freq_cap})
    print(out.with_suffix(".md").read_text())


def cmd_prep_criteo(args: argparse.Namespace) -> None:
    from adfill.sim.prices import DEFAULT_CACHE, FULL_CACHE, prepare_cache

    prepare_cache(Path(args.tsv))
    print(f"wrote {DEFAULT_CACHE} and {FULL_CACHE}")


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


def cmd_content(args: argparse.Namespace) -> None:
    from adfill.report.content import measure

    result = measure(Path(args.ml_dir), args.windows, args.seeds, args.days, args.history_days)
    out = Path("results") / f"{args.name}.json"
    out.write_text(json.dumps(result, indent=1) + "\n")
    print(json.dumps(result, indent=1))


def cmd_forecast(args: argparse.Namespace) -> None:
    from adfill.report.forecast import validate

    cfg = SimConfig(price_source="criteo-cpa", rate_model="gbm")
    result = validate(Path(args.ml_dir), args.windows, args.seeds, args.days, args.history_days, cfg)
    out = Path("results") / f"{args.name}.json"
    out.write_text(json.dumps(result, indent=1) + "\n")
    print(json.dumps(result, indent=1))


def cmd_winrate(args: argparse.Namespace) -> None:
    from adfill.report.winrate import run

    result = run(Path(args.ml_dir), args.windows, args.seeds, args.per_world, args.bid_median, args.bid_sigma)
    out = Path("results") / f"{args.name}.json"
    out.write_text(json.dumps(result, indent=1) + "\n")
    print(json.dumps(result, indent=1))


def cmd_spike(args: argparse.Namespace) -> None:
    from adfill.report.spike import run

    config = {"price_source": "criteo-cpa", "rate_model": "gbm"}
    rows = run(args.name, args.windows, args.seeds, args.multiples, args.ml_dir, args.run_dir, args.workers, config)
    out = Path("results") / f"{args.name}.json"
    out.write_text(json.dumps({"config": config, "rows": rows}, indent=1) + "\n")
    print(f"wrote {out}")


def cmd_bandit(args: argparse.Namespace) -> None:
    from adfill.bandit.creative import run as creative
    from adfill.bandit.ope import run as ope

    result = {"ope": ope(n_boot=args.boot), "creative": creative(args.flights, args.reps, args.seed)}
    out = Path("results") / f"{args.name}.json"
    out.write_text(json.dumps(result, indent=1) + "\n")
    print(json.dumps(result["ope"], indent=1))
    for n, v in result["creative"]["by_flight_impressions"].items():
        print(n, {k: (x["goal_met_share"], x["regret_share"]) for k, x in v.items()})


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
    r.add_argument("--targeting-mode", choices=["genre", "semantic"], default="genre")
    r.add_argument("--brand-safety", choices=["off", "on", "after_booking"], default="off")
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
    w.add_argument("--targeting-mode", choices=["genre", "semantic"], default="genre")
    w.add_argument("--brand-safety", choices=["off", "on", "after_booking"], default="off")
    w.add_argument("--book-share", type=float, default=0.4, help="share of forecast ad slots sold as guaranteed")
    w.add_argument("--forecast-model", choices=["naive", "seasonal"], default="naive")
    w.add_argument("--contention", action="store_true", help="discount supply by overlapping campaigns")
    w.add_argument("--forecast-bias", type=float, default=1.0, help="multiply the allocator's forecast")
    w.add_argument("--avails", action="store_true", help="trim or refuse deals that would oversell")
    w.add_argument("--avails-margin", type=float, default=0.1)
    w.add_argument("--booking-bias", type=float, default=1.0, help="multiply supply as seen at booking")
    w.add_argument("--reach-share", type=float, default=0.0, help="share of deals buying unique viewers")
    w.add_argument("--freq-cap", type=int, default=0, help="ads per viewer per campaign per 24h; 0 = off")
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

    k = sub.add_parser("content", help="brand-safety refusal and semantic-vs-genre forecast accuracy")
    k.add_argument("--name", default="content-2018")
    k.add_argument("--windows", nargs="+", default=["2018-03-01", "2018-09-01"])
    k.add_argument("--seeds", nargs="+", type=int, default=[1, 2, 3])
    k.add_argument("--days", type=int, default=30)
    k.add_argument("--history-days", type=int, default=14)
    k.add_argument("--ml-dir", default="data/ml-25m")
    k.set_defaults(func=cmd_content)

    f = sub.add_parser("forecast", help="validate naive vs seasonal forecasts on held-out periods")
    f.add_argument("--name", default="forecast-2018")
    f.add_argument("--windows", nargs="+", default=["2018-03-01", "2018-09-01"])
    f.add_argument("--seeds", nargs="+", type=int, default=[1, 2, 3])
    f.add_argument("--days", type=int, default=30)
    f.add_argument("--history-days", type=int, default=14)
    f.add_argument("--ml-dir", default="data/ml-25m")
    f.set_defaults(func=cmd_forecast)

    v = sub.add_parser("winrate", help="win-rate curve from censored feedback: winners-only vs Kaplan-Meier")
    v.add_argument("--name", default="winrate-2018")
    v.add_argument("--windows", nargs="+", default=["2018-03-01", "2018-09-01"])
    v.add_argument("--seeds", nargs="+", type=int, default=[1, 2, 3])
    v.add_argument("--per-world", type=int, default=1500)
    v.add_argument("--bid-median", type=float, default=18.0, help="buyer's median bid, $ CPM")
    v.add_argument("--bid-sigma", type=float, default=0.5)
    v.add_argument("--ml-dir", default="data/ml-25m")
    v.set_defaults(func=cmd_winrate)

    e = sub.add_parser("spike", help="live-event spike: overshoot vs arrival rate, counter sync and throttles")
    e.add_argument("--name", default="spike-2018")
    e.add_argument("--windows", nargs="+", default=["2018-03-01", "2018-09-01"])
    e.add_argument("--seeds", nargs="+", type=int, default=[1, 2, 3])
    e.add_argument("--multiples", nargs="+", type=float, default=[1.0, 3.0, 10.0, 30.0, 100.0])
    e.add_argument("--ml-dir", default="data/ml-25m")
    e.add_argument("--run-dir", default="data/runs")
    e.add_argument("--workers", type=int, default=4)
    e.set_defaults(func=cmd_spike)

    d = sub.add_parser("bandit", help="off-policy evaluation and deadline-constrained creative bandit (OBD)")
    d.add_argument("--name", default="bandit-obd")
    d.add_argument("--flights", nargs="+", type=int, default=[5_000, 10_000, 20_000, 50_000, 100_000, 200_000, 500_000])
    d.add_argument("--reps", type=int, default=1_000)
    d.add_argument("--boot", type=int, default=500)
    d.add_argument("--seed", type=int, default=1)
    d.set_defaults(func=cmd_bandit)

    c = sub.add_parser("prep-criteo", help="cache campaign and cost columns from the Criteo attribution TSV")
    c.add_argument("--tsv", default="data/criteo/criteo_attribution_dataset.tsv.gz")
    c.set_defaults(func=cmd_prep_criteo)
    args = p.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
