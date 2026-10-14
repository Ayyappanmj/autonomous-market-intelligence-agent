"""Environment-based configuration. No secrets are ever hard-coded."""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from functools import lru_cache

from app import __version__

GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai"
LLM_PROVIDERS = ("gemini", "openai_compatible")
VALID_TOPICS = ("ai", "technology", "markets", "business", "energy", "economy")
MAX_FEEDS_CONFIGURED = 40

DEFAULT_FEEDS: dict[str, str] = {
    # "Publisher / Section" -> feed URL. The part before " / " is the publisher name.
    "BBC / Business": "https://feeds.bbci.co.uk/news/business/rss.xml",
    "BBC / Technology": "https://feeds.bbci.co.uk/news/technology/rss.xml",
    "NYT / Business": "https://rss.nytimes.com/services/xml/rss/nyt/Business.xml",
    "NYT / Technology": "https://rss.nytimes.com/services/xml/rss/nyt/Technology.xml",
    "The Guardian / Business": "https://www.theguardian.com/uk/business/rss",
    "CNBC / Top News": "https://www.cnbc.com/id/100003114/device/rss/rss.html",
    "MarketWatch / Top Stories": "https://feeds.content.dowjones.io/public/rss/mw_topstories",
}


def load_env_file(path: str = ".env") -> None:
    """Minimal .env loader (no extra dependency). Real environment variables win."""
    try:
        lines = open(path, encoding="utf-8").read().splitlines()
    except OSError:
        return
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        value = value.split(" #", 1)[0].strip().strip('"').strip("'")
        os.environ.setdefault(key.strip(), value)


def parse_feed_config(data: object) -> tuple[dict[str, str], dict[str, tuple[str, ...]]]:
    """Validate a feeds.json structure. Invalid entries are skipped, never fatal.

    Returns (name -> url, name -> topic hints).
    """
    items = data.get("feeds") if isinstance(data, dict) else data
    feeds: dict[str, str] = {}
    topics: dict[str, tuple[str, ...]] = {}
    if not isinstance(items, list):
        return feeds, topics
    for item in items:
        if not isinstance(item, dict) or item.get("enabled", True) is False:
            continue
        name, url = item.get("name"), item.get("url")
        if not isinstance(name, str) or not isinstance(url, str):
            continue
        name, url = name.strip()[:80], url.strip()
        if not name or not url.lower().startswith(("http://", "https://")) or len(url) > 2048:
            continue
        if name in feeds or url in feeds.values():
            continue  # duplicate name or url
        hint = item.get("topics")
        if isinstance(hint, list):
            tags = tuple(t for t in (str(x).strip().lower() for x in hint) if t in VALID_TOPICS)
            if tags:
                topics[name] = tags
        feeds[name] = url
        if len(feeds) >= MAX_FEEDS_CONFIGURED:
            break
    return feeds, topics


def load_feeds_file(path: str) -> tuple[dict[str, str], dict[str, tuple[str, ...]]]:
    try:
        with open(path, encoding="utf-8") as fh:
            return parse_feed_config(json.load(fh))
    except (OSError, ValueError):
        return {}, {}


def select_feeds(feeds: dict[str, str], feed_topics: dict[str, tuple[str, ...]],
                 topics: list[str], limit: int) -> dict[str, str]:
    """Pick feeds relevant to the requested topics (untagged feeds always qualify), best match first."""
    wanted = set(topics)
    ranked: list[tuple[int, int, str, str]] = []
    for idx, (name, url) in enumerate(feeds.items()):
        hint = set(feed_topics.get(name, ()))
        if hint and wanted and not (hint & wanted):
            continue
        ranked.append((-len(hint & wanted), idx, name, url))
    ranked.sort()
    return {name: url for _, _, name, url in ranked[: max(1, limit)]}


def _int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, default))
    except ValueError:
        return default


def _float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, default))
    except ValueError:
        return default


def _parse_feeds(raw: str | None) -> dict[str, str]:
    """FEEDS env format: 'Name|https://url,Name2|https://url2'."""
    if not raw:
        return dict(DEFAULT_FEEDS)
    feeds: dict[str, str] = {}
    for part in raw.split(","):
        if "|" in part:
            name, url = part.split("|", 1)
            if name.strip() and url.strip():
                feeds[name.strip()] = url.strip()
    return feeds or dict(DEFAULT_FEEDS)


@dataclass(frozen=True)
class Settings:
    app_name: str = "Autonomous Market Intelligence Agent"
    version: str = __version__
    environment: str = "development"
    log_level: str = "INFO"
    database_path: str = "data/market_intel.db"
    feeds: dict[str, str] = field(default_factory=lambda: dict(DEFAULT_FEEDS))
    feed_topics: dict[str, tuple[str, ...]] = field(default_factory=dict)
    max_feeds_per_run: int = 10
    trust_proxy: bool = False
    proxy_hops: int = 1
    http_timeout_s: float = 8.0
    http_retries: int = 2
    http_backoff_s: float = 0.5
    max_feed_bytes: int = 2_000_000
    max_articles_per_run: int = 60
    max_articles_per_feed: int = 25
    cache_ttl_s: int = 600
    stale_after_hours: int = 72
    allow_private_hosts: bool = False  # SSRF guard; only enable in tests
    rate_limit_per_min: int = 30
    generate_rate_limit_per_min: int = 5
    max_request_bytes: int = 16_384
    llm_provider: str = "none"  # "none" | "gemini" | "openai_compatible"
    llm_base_url: str = "https://generativelanguage.googleapis.com/v1beta/openai"
    llm_model: str = "gemini-2.5-flash"
    llm_api_key: str = ""
    llm_timeout_s: float = 30.0
    llm_max_input_articles: int = 25
    llm_retries: int = 2
    llm_daily_budget: int = 50  # max LLM HTTP calls per UTC day (retries count) - protects free-tier quota
    llm_min_interval_s: float = 4.0  # minimum spacing between LLM calls

    @property
    def llm_configured(self) -> bool:
        return self.llm_provider in LLM_PROVIDERS and bool(self.llm_api_key.strip())


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    load_env_file()
    if os.getenv("FEEDS"):
        feeds, feed_topics = _parse_feeds(os.getenv("FEEDS")), {}
    else:
        feeds, feed_topics = load_feeds_file(os.getenv("FEEDS_FILE", "config/feeds.json"))
        if not feeds:
            feeds = dict(DEFAULT_FEEDS)
    return Settings(
        environment=os.getenv("APP_ENV", "development"),
        log_level=os.getenv("LOG_LEVEL", "INFO").upper(),
        database_path=os.getenv("DATABASE_PATH", "data/market_intel.db"),
        feeds=feeds,
        feed_topics=feed_topics,
        max_feeds_per_run=_int("MAX_FEEDS_PER_RUN", 10),
        trust_proxy=os.getenv("TRUST_PROXY", "false").strip().lower() in ("1", "true", "yes"),
        proxy_hops=max(1, _int("PROXY_HOPS", 1)),
        http_timeout_s=_float("HTTP_TIMEOUT_S", 8.0),
        http_retries=_int("HTTP_RETRIES", 2),
        max_articles_per_run=_int("MAX_ARTICLES_PER_RUN", 60),
        max_articles_per_feed=_int("MAX_ARTICLES_PER_FEED", 25),
        cache_ttl_s=_int("CACHE_TTL_S", 600),
        stale_after_hours=_int("STALE_AFTER_HOURS", 72),
        rate_limit_per_min=_int("RATE_LIMIT_PER_MIN", 30),
        generate_rate_limit_per_min=_int("GENERATE_RATE_LIMIT_PER_MIN", 5),
        llm_provider=os.getenv("LLM_PROVIDER", "none").strip().lower(),
        llm_base_url=os.getenv("LLM_BASE_URL", GEMINI_BASE_URL),
        llm_model=os.getenv("LLM_MODEL", "gemini-2.5-flash"),
        llm_api_key=os.getenv("LLM_API_KEY") or os.getenv("GEMINI_API_KEY", ""),
        llm_retries=max(0, _int("LLM_RETRIES", 2)),
        llm_daily_budget=max(1, _int("LLM_DAILY_CALL_BUDGET", 50)),
        llm_min_interval_s=max(0.0, _float("LLM_MIN_INTERVAL_S", 4.0)),
    )
