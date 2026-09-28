"""Content rules resolved for one world: brief allow-lists and per-category safety deny-lists."""

from __future__ import annotations

from dataclasses import dataclass
from functools import cache
from pathlib import Path

from adfill.content.genome import load_genome
from adfill.content.rules import BRIEFS, SAFETY_RULES, brief_titles, unsafe_titles


@dataclass(frozen=True)
class ContentIndex:
    briefs: dict[str, frozenset[int]]
    unsafe: dict[str, frozenset[int]]  # by advertiser category


@cache
def content_index(ml_dir: Path, all_titles: frozenset[int]) -> ContentIndex:
    genome = load_genome(ml_dir)
    return ContentIndex(
        briefs={b: brief_titles(genome, b) for b in BRIEFS},
        unsafe={c: unsafe_titles(genome, c, all_titles) for c in SAFETY_RULES},
    )
