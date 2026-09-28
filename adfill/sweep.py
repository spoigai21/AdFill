"""Sensitivity sweep (SPEC §8): the headline pair across worlds, urgency exponents and makegood penalties.

A world is one MovieLens window x one seed. Baseline decisions depend on neither swept parameter, so
each baseline runs once per world and is re-scored per penalty; AdFill runs once per (exponent, penalty).
"""

from __future__ import annotations

import json
from concurrent.futures import ProcessPoolExecutor
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean

from adfill.core.engine import Policy
from adfill.report.delivery import headline
from adfill.sim.config import SimConfig
from adfill.sim.runner import run_policy
from adfill.sim.world import movielens_world


def _with_penalty(campaigns, ratio):
    return [replace(c, makegood_cpm=round(c.cpm * ratio, 2)) for c in campaigns]


def run_world(task: dict) -> list[dict]:
    cfg = replace(SimConfig(seed=task["seed"]), **task.get("config", {}))
    start = int(datetime.fromisoformat(task["window"]).replace(tzinfo=timezone.utc).timestamp())
    world = movielens_world(Path(task["ml_dir"]), cfg, start, task["days"], task["history_days"], 1.0)
    base = Path(task["run_dir"]) / f"{task['window']}-s{task['seed']}"
    rows = []

    def record(policy, exponent, ratio, log, us):
        h, _ = headline(log, _with_penalty(world.campaigns, ratio))
        rows.append({"window": task["window"], "seed": task["seed"], "policy": policy.value,
                     "exponent": exponent, "makegood_ratio": ratio, "us_per_decision": round(us, 1),
                     **h.to_dict(), "world": dict(world.stats)})

    for policy in (Policy.GUARANTEED_FIRST, Policy.HIGHEST_BID):
        log = base / f"{policy.value}.jsonl"
        _, us = run_policy(world, policy, cfg, log)
        for ratio in task["makegood_ratios"]:
            record(policy, None, ratio, log, us)

    for ratio in task["makegood_ratios"]:
        w = replace(world, campaigns=_with_penalty(world.campaigns, ratio))
        for k in task["exponents"]:
            log = base / f"adfill-k{k}-mg{ratio}.jsonl"
            _, us = run_policy(w, Policy.ADFILL, replace(cfg, urgency_exponent=k), log)
            record(Policy.ADFILL, k, ratio, log, us)
    return rows


def summarize(rows: list[dict]) -> str:
    worlds = sorted({(r["window"], r["seed"]) for r in rows})
    ratios = sorted({r["makegood_ratio"] for r in rows})
    exps = sorted({r["exponent"] for r in rows if r["exponent"] is not None})
    idx = {(r["window"], r["seed"], r["policy"], r["exponent"], r["makegood_ratio"]): r for r in rows}

    lines = [f"Worlds: {len(worlds)} ({', '.join(f'{w} seed {s}' for w, s in worlds)})", ""]
    lines += ["Revenue lift vs guaranteed-first, and campaigns delivered in full (summed over worlds).", ""]
    for ratio in ratios:
        gf = [idx[(w, s, "guaranteed_first", None, ratio)] for w, s in worlds]
        hb = [idx[(w, s, "highest_bid", None, ratio)] for w, s in worlds]
        n = sum(r["campaigns"] for r in gf)
        lines.append(f"### makegood = {ratio} x contract CPM")
        lines.append("")
        lines.append("| policy | exponent | revenue lift vs GF (mean) | min | max | delivered in full | mean delivery |")
        lines.append("|---|---|---|---|---|---|---|")
        for name, rs in (("guaranteed_first", gf), ("highest_bid", hb)):
            lifts = [r["total_revenue"] / g["total_revenue"] - 1 for r, g in zip(rs, gf)]
            lines.append(f"| {name} | – | {mean(lifts):+.1%} | {min(lifts):+.1%} | {max(lifts):+.1%} | "
                         f"{sum(r['delivered_in_full'] for r in rs)}/{n} | {mean(r['mean_delivery_share'] for r in rs):.3f} |")
        for k in exps:
            rs = [idx[(w, s, "adfill", k, ratio)] for w, s in worlds]
            lifts = [r["total_revenue"] / g["total_revenue"] - 1 for r, g in zip(rs, gf)]
            lines.append(f"| adfill | {k} | {mean(lifts):+.1%} | {min(lifts):+.1%} | {max(lifts):+.1%} | "
                         f"{sum(r['delivered_in_full'] for r in rs)}/{n} | {mean(r['mean_delivery_share'] for r in rs):.3f} |")
        lines.append("")
    return "\n".join(lines)


def run_sweep(name: str, windows: list[str], seeds: list[int], exponents: list[float], ratios: list[float],
              ml_dir: str, run_dir: str, days: int, history_days: int, workers: int,
              config: dict | None = None) -> Path:
    tasks = [{"window": w, "seed": s, "exponents": exponents, "makegood_ratios": ratios, "ml_dir": ml_dir,
              "run_dir": str(Path(run_dir) / name), "days": days, "history_days": history_days,
              "config": config or {}}
             for w in windows for s in seeds]
    with ProcessPoolExecutor(workers) as pool:
        rows = [r for rs in pool.map(run_world, tasks) for r in rs]
    out = Path("results") / f"{name}.json"
    out.parent.mkdir(exist_ok=True)
    meta = {"windows": windows, "seeds": seeds, "exponents": exponents, "makegood_ratios": ratios,
            "days": days, "history_days": history_days, "config": replace(SimConfig(), **(config or {})).to_dict()}
    out.write_text(json.dumps({"meta": meta, "rows": rows}, indent=1) + "\n")
    Path("results") .joinpath(f"{name}.md").write_text(f"# Sweep: {name}\n\n" + summarize(rows) + "\n")
    return out
