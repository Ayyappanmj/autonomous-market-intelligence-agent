"""Normalise raw feed entries into validated Article objects."""
from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from typing import Any, Optional
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from app.schemas.briefing import Article
from app.utils.security import clean_text, looks_like_injection

_TRACKING = {"fbclid", "gclid", "mc_cid", "mc_eid", "ref", "cmp", "ocid", "taid", "smid", "partner"}


def normalize_url(url: str) -> str:
    """Lower-case host, drop fragments, tracking params and trailing slashes."""
    parsed = urlparse(url.strip())
    query = [
        (k, v)
        for k, v in parse_qsl(parsed.query, keep_blank_values=False)
        if not k.lower().startswith("utm_") and k.lower() not in _TRACKING
    ]
    path = parsed.path.rstrip("/") or "/"
    host = (parsed.hostname or "").lower()
    if host.startswith("www."):
        host = host[4:]
    scheme = "https" if parsed.scheme in ("http", "https") else parsed.scheme
    return urlunparse((scheme, host, path, "", urlencode(sorted(query)), ""))


def parse_date(value: Any) -> Optional[datetime]:
    """Parse RFC 822 or ISO 8601 dates into aware UTC datetimes; None if impossible."""
    if not value:
        return None
    text = str(value).strip()
    parsed: Optional[datetime] = None
    try:
        parsed = parsedate_to_datetime(text)
    except (TypeError, ValueError, IndexError):
        parsed = None
    if parsed is None:
        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def publisher_from_feed(feed_name: str) -> str:
    return clean_text(feed_name.split(" / ")[0], 80) or feed_name


def make_id(url: str) -> str:
    return hashlib.sha1(normalize_url(url).encode()).hexdigest()[:16]


def normalize_entry(
    raw: dict[str, Any], feed_name: str, collected_at: Optional[datetime] = None
) -> Optional[Article]:
    """Return an Article, or None when the entry is malformed."""
    if not isinstance(raw, dict):
        return None
    title = clean_text(raw.get("title"), 300)
    link = str(raw.get("link") or "").strip()
    if len(title) < 8 or not link:
        return None
    parsed = urlparse(link)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        return None
    summary = clean_text(raw.get("summary"), 500)
    published = parse_date(raw.get("published"))
    now = collected_at or datetime.now(timezone.utc)
    if published and published > now + timedelta(days=1):
        published = None  # implausible future date -> treat as missing
    return Article(
        id=make_id(link),
        title=title,
        publisher=publisher_from_feed(feed_name),
        url=normalize_url(link),
        summary=summary,
        published_at=published,
        collected_at=now,
        feed_name=feed_name,
        suspicious=looks_like_injection(title) or looks_like_injection(summary),
    )
