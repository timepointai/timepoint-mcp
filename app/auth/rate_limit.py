import time
from collections import defaultdict
from dataclasses import dataclass, field


@dataclass
class _Window:
    timestamps: list[float] = field(default_factory=list)


class RateLimiter:
    """In-memory sliding window rate limiter."""

    def __init__(self):
        self._windows: dict[str, _Window] = defaultdict(_Window)

    def check(self, key: str, limit: int, window_seconds: int = 60) -> tuple[bool, int]:
        """Check if a request is allowed.

        Returns (allowed, remaining).
        """
        now = time.monotonic()
        cutoff = now - window_seconds
        w = self._windows[key]
        # Prune old entries
        w.timestamps = [t for t in w.timestamps if t > cutoff]
        if len(w.timestamps) >= limit:
            return False, 0
        w.timestamps.append(now)
        remaining = limit - len(w.timestamps)
        return True, remaining

    def cleanup(self):
        """Remove stale entries. Call periodically."""
        now = time.monotonic()
        cutoff = now - 120  # 2 minute window
        stale = [k for k, v in self._windows.items() if not v.timestamps or v.timestamps[-1] < cutoff]
        for k in stale:
            del self._windows[k]
