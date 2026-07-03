"""Simple per-key rate limiter backed by Redis INCR + EXPIRE."""
from __future__ import annotations


async def check_rate_limit(redis, key: str, limit: int, window_s: int) -> bool:
    """Return True if the request is within the rate limit, False if over.

    Uses atomic INCR + conditional EXPIRE so the window slides correctly.
    On any exception the caller should FAIL OPEN (allow the request).
    """
    count = await redis.incr(key)
    if count == 1:
        # First hit in this window — set expiry.
        await redis.expire(key, window_s)
    return count <= limit
