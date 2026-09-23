"""Энгийн санах ойн (in-memory) хурдны хязгаарлалт. Нэг процесст ажиллах прототипод хангалттай."""
import threading
import time
from collections import defaultdict, deque

from fastapi import Request

_hits: dict[str, deque] = defaultdict(deque)
_lock = threading.Lock()


def allow(key: str, limit: int, window_seconds: int) -> bool:
    now = time.monotonic()
    with _lock:
        bucket = _hits[key]
        while bucket and now - bucket[0] > window_seconds:
            bucket.popleft()
        if len(bucket) >= limit:
            return False
        bucket.append(now)
        return True


def client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"
