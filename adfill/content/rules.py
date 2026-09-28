"""Semantic briefs and brand-safety rules (SPEC §5), resolved into title allow- and deny-lists.

Both are chosen parameters, documented in spec/ASSUMPTIONS.md. Resolving them to title sets when a world
is built keeps the request path a set lookup.
"""

from __future__ import annotations

import numpy as np

from adfill.content.genome import Genome

# A brief is what an advertiser buys instead of genres. A title matches if the mean relevance of the
# brief's tags reaches BRIEF_THRESHOLD.
BRIEFS: dict[str, tuple[str, ...]] = {
    "feel_good_family": ("feel-good", "family", "heartwarming"),
    "inspirational": ("inspirational", "inspiring", "thought-provoking"),
    "adrenaline": ("action", "fast paced", "intense"),
    "suspense": ("suspense", "tense", "twist ending"),
    "laughs": ("funny", "comedy", "very funny"),
    "romance": ("romance", "romantic comedy", "cute"),
    "big_screen": ("epic", "visually appealing", "beautiful scenery"),
    "sci_fi_future": ("sci-fi", "futuristic", "intelligent sci-fi"),
    "music": ("music", "great music", "musical"),
    "young_audience": ("teen", "high school", "coming of age"),
}
BRIEF_THRESHOLD = 0.5

# Brand safety: a title is refused for a category if any listed tag's relevance reaches its threshold.
_EVERYONE = {"gore": 0.8, "sexualized violence": 0.6, "child abuse": 0.6, "rape": 0.6}
SAFETY_RULES: dict[str, dict[str, float]] = {
    "travel": {**_EVERYONE, "disaster": 0.7, "natural disaster": 0.6, "terrorism": 0.6, "airplane": 0.8},
    "fast_food": {**_EVERYONE, "drug addiction": 0.7, "disturbing": 0.8},
    "beverage": {**_EVERYONE, "alcoholism": 0.6, "drug addiction": 0.7},
    "pharma": {**_EVERYONE, "suicide": 0.5, "depression": 0.6, "drug abuse": 0.6, "cancer": 0.6},
    "finance": {**_EVERYONE, "bank robbery": 0.7},
    "cpg": {**_EVERYONE, "disturbing": 0.8, "violent": 0.9},
    "auto": {**_EVERYONE, "disaster": 0.8},
    "telecom": {**_EVERYONE, "terrorism": 0.7},
    "retail": dict(_EVERYONE),
    "tech": dict(_EVERYONE),
}


def brief_titles(genome: Genome, brief: str) -> frozenset[int]:
    ok = genome.score(BRIEFS[brief]) >= BRIEF_THRESHOLD
    return frozenset(genome.titles[ok].tolist())


def unsafe_titles(genome: Genome, category: str, all_titles: frozenset[int]) -> frozenset[int]:
    """Titles refused for `category`: those tripping a rule, plus those with no genome (unverifiable)."""
    unsafe = np.zeros(len(genome.titles), dtype=bool)
    for tag, threshold in SAFETY_RULES[category].items():
        unsafe |= genome.relevance[:, genome.tags[tag]] >= threshold
    verified = frozenset(genome.titles.tolist())
    return frozenset(genome.titles[unsafe].tolist()) | (all_titles - verified)
