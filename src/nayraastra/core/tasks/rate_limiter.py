"""Asynchronous token bucket rate limiter."""

from __future__ import annotations

import asyncio
import time


class AsyncRateLimiter:
    """Token bucket rate limiter for asyncio task execution."""

    def __init__(self, rate_per_second: float = 10.0) -> None:
        self.rate = rate_per_second
        self._tokens = float(rate_per_second) if rate_per_second > 0 else float("inf")
        self._last_time = time.monotonic()
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        """Wait until an execution token is available."""
        if self.rate <= 0:
            return

        async with self._lock:
            while True:
                now = time.monotonic()
                elapsed = now - self._last_time
                self._last_time = now

                self._tokens = min(self.rate, self._tokens + elapsed * self.rate)
                if self._tokens >= 1.0:
                    self._tokens -= 1.0
                    return

                # Wait for next token
                needed = (1.0 - self._tokens) / self.rate
                await asyncio.sleep(max(0.001, needed))
