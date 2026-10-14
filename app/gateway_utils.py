"""Pure, dependency-free helpers for the gateway and rate limiter (unit-testable without a web stack)."""
from __future__ import annotations

from typing import Iterable, Optional

HOP_BY_HOP = {
    "connection", "keep-alive", "proxy-authenticate", "proxy-authorization", "te", "trailer",
    "transfer-encoding", "upgrade",
}


def filter_headers(headers: Iterable[tuple[str, str]], drop: Iterable[str] = ()) -> list[tuple[str, str]]:
    """Remove hop-by-hop headers (and any names in `drop`). Duplicate headers (Set-Cookie) are preserved."""
    blocked = HOP_BY_HOP | {d.lower() for d in drop}
    return [(k, v) for k, v in headers if k.lower() not in blocked]


def upstream_url(base: str, path: str, query: str = "") -> str:
    """Join a fixed upstream base with a request path. The host can never be changed by the path:
    '//evil.example/x' becomes '/evil.example/x' on the fixed upstream."""
    clean = "/" + path.replace("\\", "/").lstrip("/")
    url = base.rstrip("/") + clean
    return f"{url}?{query}" if query else url


def extract_client_ip(peer: Optional[str], forwarded_for: Optional[str], trust_proxy: bool, hops: int = 1) -> str:
    """Pick the client address for rate limiting.

    Without trust_proxy only the TCP peer is used (X-Forwarded-For is client-controlled and ignored).
    With trust_proxy, use the entry `hops` places from the right: the address your own trusted
    proxy(ies) observed, which a client cannot forge by sending its own header.
    """
    if trust_proxy and forwarded_for:
        parts = [p.strip() for p in forwarded_for.split(",") if p.strip()]
        if parts:
            return parts[max(0, len(parts) - max(1, hops))][:64]
    return peer or "unknown"
