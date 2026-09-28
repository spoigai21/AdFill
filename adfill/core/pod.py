"""Pod construction: choose and order the ads that fill one break (SPEC §3).

A legal pod
  1. fits the break: total duration in [length - tolerance, length]
  2. has at most one ad per advertiser
  3. never puts two ads of the same category next to each other
and the solver returns the highest-value legal pod.

Constraint 3 is about order, but it reduces to a property of the set: n ads can be ordered with no two
same-category neighbours iff no category holds more than ceil(n / 2) of them. So the exact solver picks
a set under that count limit, then `order_pod` lays it out.

Each advertiser belongs to exactly one category (an input invariant, checked). That lets the exact
solver go category by category: inside a category, a group knapsack picks at most one creative per
advertiser; across categories, a DP over (duration, count, largest category count) combines them.
"""

from __future__ import annotations

import itertools
from collections import Counter, defaultdict
from dataclasses import dataclass
from math import gcd

from adfill.core.model import Candidate

_EPS = 1e-9


@dataclass(frozen=True)
class Pod:
    items: tuple[Candidate, ...]  # in play order

    @property
    def duration_s(self) -> int:
        return sum(c.duration_s for c in self.items)

    @property
    def value(self) -> float:
        return sum(c.value for c in self.items)


EMPTY_POD = Pod(())


def _max_share_ok(counts: Counter, n: int) -> bool:
    return all(k <= (n + 1) // 2 for k in counts.values())


def is_legal_set(items: tuple[Candidate, ...] | list[Candidate], length: int, tolerance: int = 0) -> bool:
    total = sum(c.duration_s for c in items)
    if not (length - tolerance <= total <= length):
        return False
    advertisers = [c.advertiser for c in items]
    if len(set(advertisers)) != len(advertisers):
        return False
    return _max_share_ok(Counter(c.category for c in items), len(items))


def is_legal_pod(pod: Pod, length: int, tolerance: int = 0) -> bool:
    if not is_legal_set(pod.items, length, tolerance):
        return False
    return all(a.category != b.category for a, b in zip(pod.items, pod.items[1:]))


def _check_advertiser_categories(cands: list[Candidate]) -> None:
    seen: dict[str, str] = {}
    for c in cands:
        if seen.setdefault(c.advertiser, c.category) != c.category:
            raise ValueError(f"advertiser {c.advertiser!r} appears in two categories")


def _arrangeable(counts: Counter, forbidden_first: str | None) -> bool:
    """Can these category counts be laid out with no equal neighbours, not starting with `forbidden_first`?"""
    r = sum(counts.values())
    for cat, k in counts.items():
        limit = r // 2 if cat == forbidden_first else (r + 1) // 2
        if k > limit:
            return False
    return True


def order_pod(items: list[Candidate] | tuple[Candidate, ...]) -> Pod:
    """Most valuable ad first, subject to competitive separation.

    At each position take the highest-value remaining ad whose category differs from the previous one
    and whose removal leaves the rest still arrangeable. Raises if the set is not arrangeable at all.
    """
    remaining = sorted(items, key=lambda c: (-c.value, c.ref))
    counts = Counter(c.category for c in remaining)
    if not _arrangeable(counts, None):
        raise ValueError("no ordering satisfies competitive separation")
    out: list[Candidate] = []
    last: str | None = None
    while remaining:
        for i, c in enumerate(remaining):
            if c.category == last:
                continue
            counts[c.category] -= 1
            if _arrangeable(+counts, c.category):
                out.append(remaining.pop(i))
                last = c.category
                break
            counts[c.category] += 1
        else:  # unreachable when the invariant holds
            raise AssertionError("ordering invariant violated")
    return Pod(tuple(out))


def solve_exact(cands: list[Candidate], length: int, tolerance: int = 0) -> Pod | None:
    """Highest-value legal pod, or None if no legal pod exists."""
    cands = [c for c in cands if 0 < c.duration_s <= length]
    if any(c.value < 0 for c in cands):
        raise ValueError("candidate values must be non-negative")
    _check_advertiser_categories(cands)
    if not cands:
        return EMPTY_POD if length - tolerance <= 0 else None

    unit = length
    for c in cands:
        unit = gcd(unit, c.duration_s)
    D = length // unit
    n_max = D // min(c.duration_s // unit for c in cands)
    m_cap = (n_max + 1) // 2

    by_cat: dict[str, dict[str, list[Candidate]]] = defaultdict(lambda: defaultdict(list))
    for c in sorted(cands, key=lambda c: (c.category, c.advertiser, c.ref)):
        by_cat[c.category][c.advertiser].append(c)

    # F[(d, n, m)] = (value, items): best selection so far using d duration units, n ads,
    # and at most m ads from any single category.
    F: dict[tuple[int, int, int], tuple[float, tuple[Candidate, ...]]] = {(0, 0, 0): (0.0, ())}

    for cat in sorted(by_cat):
        # Group knapsack inside this category: g[(d, j)] = best j ads, distinct advertisers.
        g: dict[tuple[int, int], tuple[float, tuple[Candidate, ...]]] = {(0, 0): (0.0, ())}
        for adv in sorted(by_cat[cat]):
            new = dict(g)
            for (d, j), (v, it) in g.items():
                if j >= m_cap:
                    continue
                for c in by_cat[cat][adv]:
                    nd = d + c.duration_s // unit
                    if nd > D:
                        continue
                    key, nv = (nd, j + 1), v + c.value
                    if key not in new or nv > new[key][0] + _EPS:
                        new[key] = (nv, it + (c,))
            g = new

        newF = dict(F)
        for (d, n, m), (v, it) in F.items():
            for (d2, j), (v2, it2) in g.items():
                if j == 0:
                    continue
                nd, nn = d + d2, n + j
                if nd > D or nn > n_max:
                    continue
                key, nv = (nd, nn, max(m, j)), v + v2
                if key not in newF or nv > newF[key][0] + _EPS:
                    newF[key] = (nv, it + it2)
        F = newF

    best: tuple[float, tuple[Candidate, ...]] | None = None
    for (d, n, m), (v, it) in F.items():
        if not (length - tolerance <= d * unit <= length):
            continue
        if m > (n + 1) // 2:
            continue
        if best is None or v > best[0] + _EPS:
            best = (v, it)
    return None if best is None else order_pod(best[1])


def solve_greedy(cands: list[Candidate], length: int) -> Pod:
    """Baseline: take ads in value order while they fit and keep the set legal. May not fill the break."""
    chosen: list[Candidate] = []
    used, advertisers = 0, set()
    counts: Counter = Counter()
    for c in sorted(cands, key=lambda c: (-c.value, c.ref)):
        if used + c.duration_s > length or c.advertiser in advertisers:
            continue
        counts[c.category] += 1
        if not _max_share_ok(counts, len(chosen) + 1):
            counts[c.category] -= 1
            continue
        chosen.append(c)
        used += c.duration_s
        advertisers.add(c.advertiser)
    return order_pod(chosen)


def solve_brute(cands: list[Candidate], length: int, tolerance: int = 0) -> Pod | None:
    """Reference solver for tests: enumerate every subset."""
    best: tuple[float, tuple[Candidate, ...]] | None = None
    for r in range(len(cands) + 1):
        for subset in itertools.combinations(cands, r):
            if not is_legal_set(subset, length, tolerance):
                continue
            v = sum(c.value for c in subset)
            if best is None or v > best[0] + _EPS:
                best = (v, subset)
    return None if best is None else order_pod(best[1])
