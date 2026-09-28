"""Per-viewer ad load: at most `max_seconds` of ads in any trailing `window_s` of viewing."""

from __future__ import annotations

from collections import defaultdict, deque


class AdLoadTracker:
    def __init__(self, max_seconds: int, window_s: int = 3600):
        self.max_seconds = max_seconds
        self.window_s = window_s
        self._served: dict[int, deque[tuple[int, int]]] = defaultdict(deque)

    def _expire(self, viewer: int, t: int) -> deque[tuple[int, int]]:
        q = self._served[viewer]
        while q and q[0][0] <= t - self.window_s:
            q.popleft()
        return q

    def remaining(self, viewer: int, t: int) -> int:
        q = self._expire(viewer, t)
        return max(0, self.max_seconds - sum(s for _, s in q))

    def record(self, viewer: int, t: int, seconds: int) -> None:
        if seconds > 0:
            self._served[viewer].append((t, seconds))


class FrequencyCaps:
    """Per campaign and viewer: at most `cap` ads in any trailing `window_s`. Uncapped campaigns cost nothing."""

    def __init__(self) -> None:
        self._seen: dict[tuple[str, int], deque[int]] = defaultdict(deque)

    def allowed(self, campaign_id: str, cap: int, window_s: int, viewer: int, t: int) -> bool:
        if cap <= 0:
            return True
        q = self._seen.get((campaign_id, viewer))
        if not q:
            return True
        while q and q[0] <= t - window_s:
            q.popleft()
        return len(q) < cap

    def record(self, campaign_id: str, viewer: int, t: int) -> None:
        self._seen[(campaign_id, viewer)].append(t)
