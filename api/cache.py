"""Small hand-written cache for one expensive, argument-less computation --
not a general caching framework. Moved out of api/main.py so every router
module can import it without importing all of main.py's routes
(docs/superpowers/specs/2026-07-17-api-main-router-split-design.md).
"""
import time


class TTLCache:
    """60s bounds staleness to roughly one minute after a mid-session
    sync/analysis batch changes the underlying data, rather than caching
    until process restart (functools.lru_cache with no TTL was considered
    and rejected for this reason -- see the Overview identity-zone port
    design spec)."""

    def __init__(self, ttl_seconds):
        self._ttl_seconds = ttl_seconds
        self._value = None
        self._computed_at = None

    def get(self, compute):
        now = time.monotonic()
        if self._computed_at is None or (now - self._computed_at) > self._ttl_seconds:
            self._value = compute()
            self._computed_at = now
        return self._value

    def clear(self):
        self._value = None
        self._computed_at = None
