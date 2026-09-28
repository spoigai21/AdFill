"""Domain types for the decision path. Plain data, no I/O."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

SECONDS_PER_DAY = 86_400


class Kind(str, Enum):
    GUARANTEED = "guaranteed"
    PROGRAMMATIC = "programmatic"


@dataclass(frozen=True, slots=True)
class Creative:
    id: str
    duration_s: int


@dataclass(frozen=True, slots=True)
class Targeting:
    """None on a dimension means unrestricted."""

    genres: frozenset[str] | None = None
    devices: frozenset[str] | None = None


@dataclass(frozen=True, slots=True)
class Campaign:
    """A guaranteed deal: `goal` impressions between `start` and `end` (unix seconds)."""

    id: str
    advertiser: str
    category: str
    creatives: tuple[Creative, ...]
    goal: int
    start: int
    end: int
    targeting: Targeting
    cpm: float
    makegood_cpm: float

    @property
    def skip_cost_per_imp(self) -> float:
        """What one undelivered impression costs: the payment forgone plus the makegood owed."""
        return (self.cpm + self.makegood_cpm) / 1000.0


@dataclass(frozen=True, slots=True)
class Bid:
    """A programmatic bid for one slot in one specific break.

    A plain bid pays `cpm` per thousand impressions. A performance bid (`cpa` set) pays `cpa` only if
    the impression converts; its `cpm` is then the expected value under the predicted conversion rate,
    which is what the allocator ranks by, while `paid` is what actually arrives.
    """

    id: str
    advertiser: str
    category: str
    creative: Creative
    cpm: float
    cpa: float | None = None
    converted: bool = False

    @property
    def paid(self) -> float:
        if self.cpa is None:
            return self.cpm / 1000.0
        return self.cpa if self.converted else 0.0


@dataclass(frozen=True, slots=True)
class Break:
    """One ad break in one viewer's session, with the programmatic demand that arrived for it."""

    id: str
    viewer: int
    title: int
    genres: frozenset[str]
    device: str
    t: int
    length_s: int
    bids: tuple[Bid, ...] = field(default=())


@dataclass(frozen=True, slots=True)
class Candidate:
    """Anything that could fill one slot of a pod, already priced on the common value scale."""

    kind: Kind
    ref: str
    advertiser: str
    category: str
    duration_s: int
    value: float
    price_cpm: float
    paid: float = 0.0  # realised programmatic payment if served; guaranteed is billed from delivery
