from __future__ import annotations

import time


class TokenBucket:
    __slots__ = ("rate", "capacity", "tokens", "last_refill")

    def __init__(self, rate: float, capacity: float) -> None:
        self.rate = rate
        self.capacity = capacity
        self.tokens = capacity
        self.last_refill = time.monotonic()

    def consume(self, tokens: float = 1.0) -> bool:
        self._refill()
        if self.tokens >= tokens:
            self.tokens -= tokens
            return True
        return False

    def time_until_available(self, tokens: float = 1.0) -> float:
        self._refill()
        if self.tokens >= tokens:
            return 0.0
        deficit = tokens - self.tokens
        return deficit / self.rate

    def _refill(self) -> None:
        now = time.monotonic()
        elapsed = now - self.last_refill
        self.tokens = min(self.capacity, self.tokens + elapsed * self.rate)
        self.last_refill = now


class ApiRateLimiter:
    _buckets: dict[str, TokenBucket]

    ENDPOINTS = {
        "gamma_markets": {"rate": 2.0, "capacity": 10},
        "gamma_price": {"rate": 5.0, "capacity": 20},
        "clob_orderbook": {"rate": 5.0, "capacity": 15},
        "rss_feed": {"rate": 0.5, "capacity": 5},
    }

    def __init__(self) -> None:
        self._buckets = {}
        for ep, cfg in self.ENDPOINTS.items():
            self._buckets[ep] = TokenBucket(cfg["rate"], cfg["capacity"])

    def acquire(self, endpoint: str, tokens: float = 1.0) -> bool:
        bucket = self._buckets.get(endpoint)
        if bucket is None:
            return True
        return bucket.consume(tokens)

    def wait_if_needed(self, endpoint: str, tokens: float = 1.0) -> None:
        bucket = self._buckets.get(endpoint)
        if bucket is None:
            return
        wait = bucket.time_until_available(tokens)
        if wait > 0:
            time.sleep(wait + 0.05)
        bucket.consume(tokens)
