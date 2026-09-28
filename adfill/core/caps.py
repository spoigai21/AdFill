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
