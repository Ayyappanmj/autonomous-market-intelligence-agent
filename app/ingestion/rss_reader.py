"""Resilient RSS/Atom reader: SSRF checks, size caps, timeouts, retries with backoff, caching."""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Optional
from urllib.parse import urljoin

import requests
from defusedxml import ElementTree as ET  # blocks XML entity-expansion attacks

from app.config import Settings
from app.utils.logging import get_logger
from app.utils.security import UnsafeURLError, validate_public_url

log = get_logger(__name__)
USER_AGENT = "MarketIntelAgent/1.0 (portfolio project; RSS reader)"
MAX_REDIRECTS = 3


@dataclass
class FeedResult:
    feed_name: str
    url: str
    entries: list[dict[str, Any]] = field(default_factory=list)
    error: Optional[str] = None
    from_cache: bool = False


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1] if isinstance(tag, str) else ""


def _child_text(node, *names: str) -> str:
    for child in node:
        if _local(child.tag) in names and (child.text or "").strip():
            return child.text.strip()
    return ""


def parse_feed_xml(content: bytes, max_entries: int = 50) -> list[dict[str, Any]]:
    """Parse RSS 2.0 or Atom into raw dicts. Raises ValueError on invalid XML."""
    try:
        root = ET.fromstring(content)
    except Exception as exc:  # defusedxml raises several exception types
        raise ValueError("invalid feed xml") from exc
    entries: list[dict[str, Any]] = []
    for node in root.iter():
        name = _local(node.tag)
        if name not in ("item", "entry"):
            continue
        link = _child_text(node, "link")
        if not link:  # Atom: <link href="..."/>
            for child in node:
                if _local(child.tag) == "link" and child.get("href"):
                    link = child.get("href")
                    break
        entries.append(
            {
                "title": _child_text(node, "title"),
                "link": link,
                "summary": _child_text(node, "description", "summary", "content"),
                "published": _child_text(node, "pubDate", "published", "updated", "date"),
            }
        )
        if len(entries) >= max_entries:
            break
    return entries


class FeedFetcher:
    def __init__(self, settings: Settings, session: Optional[requests.Session] = None):
        self.settings = settings
        self.session = session or requests.Session()
        self._cache: dict[str, tuple[float, FeedResult]] = {}

    def _get(self, url: str) -> bytes:
        """GET with manual, validated redirects and a hard byte cap."""
        current = url
        for _ in range(MAX_REDIRECTS + 1):
            validate_public_url(current, self.settings.allow_private_hosts)
            resp = self.session.get(
                current,
                timeout=self.settings.http_timeout_s,
                headers={"User-Agent": USER_AGENT, "Accept": "application/rss+xml, application/xml, text/xml"},
                allow_redirects=False,
                stream=True,
            )
            if resp.status_code in (301, 302, 303, 307, 308):
                location = resp.headers.get("Location")
                if not location:
                    raise ValueError("redirect without location")
                current = urljoin(current, location)
                continue
            if resp.status_code != 200:
                raise ValueError(f"http status {resp.status_code}")
            body = b""
            for chunk in resp.iter_content(chunk_size=16_384):
                body += chunk
                if len(body) > self.settings.max_feed_bytes:
                    raise ValueError("feed exceeds size limit")
            return body
        raise ValueError("too many redirects")

    def fetch(self, feed_name: str, url: str) -> FeedResult:
        cached = self._cache.get(url)
        if cached and time.time() - cached[0] < self.settings.cache_ttl_s:
            hit = cached[1]
            return FeedResult(feed_name, url, list(hit.entries), hit.error, from_cache=True)

        last_error = "unknown error"
        attempts = self.settings.http_retries + 1
        for attempt in range(attempts):
            try:
                body = self._get(url)
                entries = parse_feed_xml(body, self.settings.max_articles_per_feed)
                result = FeedResult(feed_name, url, entries)
                self._cache[url] = (time.time(), result)
                return result
            except UnsafeURLError:
                last_error = "feed url rejected by security policy"
                break  # never retry unsafe URLs
            except requests.Timeout:
                last_error = "timeout"
            except requests.RequestException:
                last_error = "network error"
            except ValueError as exc:
                last_error = str(exc)
            if attempt < attempts - 1:
                time.sleep(self.settings.http_backoff_s * (2**attempt))
        log.warning("feed unavailable", extra={"feed": feed_name, "reason": last_error})
        return FeedResult(feed_name, url, [], error=last_error)

    def fetch_all(self, feeds: dict[str, str]) -> list[FeedResult]:
        return [self.fetch(name, url) for name, url in feeds.items()]
