"""A small in-memory sliding-window rate limiter for the public chat endpoint.

Protects the Anthropic bill on a public URL. In-memory means it resets on restart and is per process,
which is fine for a single demo instance; several instances would need a shared store (e.g. Redis).
"""

import threading
import time
from collections import defaultdict, deque


class RateLimiter:
    def __init__(self, max_requests: int, window_seconds: float, clock=time.monotonic):
        if max_requests < 1 or window_seconds <= 0:
            raise ValueError("max_requests must be >= 1 and window_seconds > 0")
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._clock = clock
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()  # FastAPI runs sync endpoints in a thread pool

    def allow(self, key: str) -> bool:
        """Record a request for `key` and return False if it is over the limit for the current window."""
        now = self._clock()
        with self._lock:
            hits = self._hits[key]
            while hits and hits[0] <= now - self.window_seconds:
                hits.popleft()
            if len(hits) >= self.max_requests:
                return False
            hits.append(now)
            return True
