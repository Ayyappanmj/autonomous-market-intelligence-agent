"""Small in-memory sliding-window rate limiter (per client IP, per bucket)."""
from __future__ import annotations

import threading
import time
from collections import defaultdict, deque

from fastapi import HTTPException, Request

from app.gateway_utils import extract_client_ip


class RateLimiter:
    def __init__(self) -> None:
        self._hits: dict[tuple[str, str], deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def check(self, key: str, bucket: str, limit: int, window_s: float = 60.0) -> None:
        now = time.monotonic()
        with self._lock:
            q = self._hits[(key, bucket)]
            while q and now - q[0] > window_s:
                q.popleft()
            if len(q) >= limit:
                raise HTTPException(status_code=429, detail="Too many requests. Please retry shortly.",
                                    headers={"Retry-After": "60"})
            q.append(now)
            if len(self._hits) > 5000:  # bound memory
                for k in [k for k, v in self._hits.items() if not v][:1000]:
                    self._hits.pop(k, None)


def client_ip(request: Request) -> str:
    st = request.app.state.settings
    return extract_client_ip(
        request.client.host if request.client else None,
        request.headers.get("x-forwarded-for"),
        st.trust_proxy,
        st.proxy_hops,
    )
