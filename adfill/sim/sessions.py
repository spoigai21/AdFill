"""Viewing sessions: who watched what, when. Real (MovieLens) or synthetic (tests, smoke runs)."""

from __future__ import annotations

from functools import cache
from pathlib import Path

import numpy as np
import pandas as pd

from adfill.core.model import SECONDS_PER_DAY

SESSION_COLUMNS = ["viewer", "title", "t"]


def load_titles(ml_dir: Path) -> dict[int, frozenset[str]]:
    movies = pd.read_csv(ml_dir / "movies.csv", usecols=["movieId", "genres"])
    return {
        int(m): frozenset(g for g in genres.split("|") if g != "(no genres listed)")
        for m, genres in zip(movies.movieId, movies.genres, strict=True)
    }


@cache
def _ratings(ml_dir: Path) -> pd.DataFrame:
    return pd.read_csv(
        ml_dir / "ratings.csv",
        usecols=["userId", "movieId", "timestamp"],
        dtype={"userId": "int32", "movieId": "int32", "timestamp": "int64"},
        engine="pyarrow",
    )


def load_movielens_sessions(
    ml_dir: Path,
    start: int,
    end: int,
    viewer_fraction: float,
    max_per_viewer_day: int,
    seed: int,
) -> pd.DataFrame:
    """One session per rating event in [start, end), for a deterministic sample of viewers.

    Users often rate dozens of titles in one sitting, which is not viewing. Keeping only the first
    `max_per_viewer_day` ratings per viewer per day turns rating bursts into a plausible watch pattern.
    """
    r = _ratings(ml_dir)
    r = r[(r.timestamp >= start) & (r.timestamp < end)]
    viewers = np.sort(r.userId.unique())
    rng = np.random.default_rng([seed, 0x5E55])
    keep = viewers[rng.random(len(viewers)) < viewer_fraction]
    r = r[r.userId.isin(keep)]
    r = r.sort_values(["userId", "timestamp", "movieId"], kind="stable")
    day = r.timestamp // SECONDS_PER_DAY
    r = r[r.groupby([r.userId, day]).cumcount() < max_per_viewer_day]
    out = r.rename(columns={"userId": "viewer", "movieId": "title", "timestamp": "t"})[SESSION_COLUMNS]
    return out.sort_values(["t", "viewer", "title"], kind="stable").reset_index(drop=True)


SYNTHETIC_GENRES = ("Drama", "Comedy", "Thriller", "Action", "Romance", "Crime", "Sci-Fi", "Horror")


def synthetic_world_sessions(
    rng: np.random.Generator, n_viewers: int, n_titles: int, start: int, days: int, sessions_per_day: float
) -> tuple[pd.DataFrame, dict[int, frozenset[str]]]:
    """Small fake catalogue and uniform viewing, for tests and quick runs."""
    titles = {
        t: frozenset(rng.choice(SYNTHETIC_GENRES, size=rng.integers(1, 3), replace=False).tolist())
        for t in range(n_titles)
    }
    n = rng.poisson(sessions_per_day * days)
    df = pd.DataFrame(
        {
            "viewer": rng.integers(0, n_viewers, n),
            "title": rng.integers(0, n_titles, n),
            "t": start + rng.integers(0, days * SECONDS_PER_DAY, n),
        }
    )
    return df.sort_values(["t", "viewer", "title"], kind="stable").reset_index(drop=True), titles
