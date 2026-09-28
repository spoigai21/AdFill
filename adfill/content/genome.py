"""The MovieLens tag genome: measured relevance of 1,128 tags to each of 13,816 titles."""

from __future__ import annotations

from dataclasses import dataclass
from functools import cache
from pathlib import Path

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class Genome:
    titles: np.ndarray  # movieId per row
    tags: dict[str, int]  # tag name -> column
    relevance: np.ndarray  # (titles, tags), float32 in [0, 1]

    def score(self, tags: tuple[str, ...]) -> np.ndarray:
        """Per title: mean relevance of `tags`. Raises on an unknown tag rather than silently scoring 0."""
        missing = [t for t in tags if t not in self.tags]
        if missing:
            raise KeyError(f"unknown genome tags: {missing}")
        return self.relevance[:, [self.tags[t] for t in tags]].mean(axis=1)


@cache
def load_genome(ml_dir: Path) -> Genome:
    tags = pd.read_csv(ml_dir / "genome-tags.csv")
    scores = pd.read_csv(ml_dir / "genome-scores.csv", engine="pyarrow")
    titles = np.sort(scores.movieId.unique())
    rel = np.zeros((len(titles), len(tags)), dtype=np.float32)
    rows = np.searchsorted(titles, scores.movieId.to_numpy())
    rel[rows, scores.tagId.to_numpy() - 1] = scores.relevance.to_numpy(np.float32)
    return Genome(titles, {t: int(i) - 1 for i, t in zip(tags.tagId, tags.tag)}, rel)
