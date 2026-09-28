# AdFill

A decision engine for ad breaks in streaming video, for the case where two incompatible kinds of demand
want the same slot: **guaranteed** campaigns whose impressions were sold months ahead, and
**programmatic** bids arriving right now. AdFill prices a promise by what it would cost to break it, so
it can compete with cash on one scale; fills each break with a legal pod (exact length, one ad per
advertiser, no competitors back to back); and measures the result against the two obvious simple rules.

The design is in [`spec/SPEC.md`](spec/SPEC.md).

## Status

Phase 1 (the allocator) is in progress. Results are not yet published; see [`spec/NUMBERS.md`](spec/NUMBERS.md).

## Run it

```sh
uv sync
uv run pytest
uv run adfill run --name demo --source synthetic
uv run adfill run --name ml --source movielens --ml-dir data/ml-25m --start 2016-03-01 --days 30
```

The MovieLens source needs [MovieLens 25M](https://grouplens.org/datasets/movielens/25m/) unpacked at
`data/ml-25m/`.

## Limitations

1. The viewers are **simulated**. Viewing sessions are derived from MovieLens rating events; nobody
   watched anything.
2. Break structure, creative durations, device classes, programmatic prices and deal terms are
   **synthesized** by the rules in [`spec/ASSUMPTIONS.md`](spec/ASSUMPTIONS.md).
3. The makegood penalty is a **chosen parameter**, not a market fact.
4. Timing figures are **per-decision costs on one machine**, not throughput claims.
