"""Security helpers: SSRF-safe URL validation, text sanitising, prompt-injection screening."""
from __future__ import annotations

import html
import ipaddress
import re
import socket
from urllib.parse import urlparse

_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")
_CTRL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")

_INJECTION_PATTERNS = [
    re.compile(p, re.I)
    for p in (
        r"ignore (all |any )?(previous|prior|above) (instructions|prompts)",
        r"disregard (the |all )?(system|previous) (prompt|instructions)",
        r"\byou are now\b",
        r"system prompt",
        r"reveal (your )?(instructions|prompt|api key)",
        r"<\s*/?\s*(system|assistant|instructions?)\s*>",
        r"\[\s*inst\s*\]",
    )
]


class UnsafeURLError(ValueError):
    """Raised when a URL fails SSRF validation."""


def validate_public_url(url: str, allow_private: bool = False) -> str:
    """Allow only http(s) URLs whose host resolves to public IP addresses."""
    if not isinstance(url, str) or len(url) > 2048:
        raise UnsafeURLError("invalid url")
    parsed = urlparse(url.strip())
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise UnsafeURLError("only http(s) urls are allowed")
    if parsed.username or parsed.password:
        raise UnsafeURLError("credentials in url are not allowed")
    if allow_private:
        return url.strip()
    try:
        infos = socket.getaddrinfo(
            parsed.hostname, parsed.port or (443 if parsed.scheme == "https" else 80)
        )
    except socket.gaierror as exc:
        raise UnsafeURLError("host cannot be resolved") from exc
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_reserved
            or ip.is_multicast
            or ip.is_unspecified
        ):
            raise UnsafeURLError("host resolves to a non-public address")
    return url.strip()


def clean_text(value: str | None, max_len: int = 600) -> str:
    """Strip HTML/control characters, collapse whitespace, truncate."""
    if not value:
        return ""
    text = html.unescape(str(value))
    text = _TAG_RE.sub(" ", text)
    text = _CTRL_RE.sub("", text)
    text = _WS_RE.sub(" ", text).strip()
    return text[:max_len]


def looks_like_injection(text: str) -> bool:
    return any(p.search(text or "") for p in _INJECTION_PATTERNS)


def neutralize_for_prompt(text: str) -> str:
    """Make untrusted text inert inside a delimited data block."""
    return text.replace("```", "'''").replace("<", "‹").replace(">", "›")
