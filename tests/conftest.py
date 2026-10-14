from __future__ import annotations

from datetime import datetime, timezone

import pytest
import requests

from app.config import Settings
from app.ingestion.rss_reader import FeedFetcher
from app.storage.repository import SQLiteRepository

NOW = datetime(2026, 10, 2, 12, 0, tzinfo=timezone.utc)


def rss(items: list[tuple[str, str, str, str]]) -> bytes:
    body = "".join(
        f"<item><title>{t}</title><link>{link}</link><description>{d}</description><pubDate>{p}</pubDate></item>"
        for t, link, d, p in items
    )
    return f'<?xml version="1.0"?><rss version="2.0"><channel><title>x</title>{body}</channel></rss>'.encode()


class FakeResponse:
    def __init__(self, content: bytes = b"", status_code: int = 200, headers: dict | None = None):
        self.content, self.status_code, self.headers = content, status_code, headers or {}

    def iter_content(self, chunk_size: int = 1024):
        for i in range(0, len(self.content), chunk_size):
            yield self.content[i:i + chunk_size]


class FakeSession:
    """Maps URL -> bytes | Exception | FakeResponse. Counts calls. No network is ever used."""

    def __init__(self, routes: dict):
        self.routes, self.calls = routes, []

    def get(self, url, **kwargs):
        self.calls.append(url)
        value = self.routes.get(url)
        if value is None:
            return FakeResponse(status_code=404)
        if isinstance(value, Exception):
            raise value
        return value if isinstance(value, FakeResponse) else FakeResponse(value)


class FakeLLM:
    name = "fake-llm"

    def __init__(self, responses: list[dict] | None = None, fail: bool = False):
        self.responses, self.fail, self.prompts = list(responses or []), fail, []

    def complete_json(self, system: str, user: str) -> dict:
        from app.agents.llm import LLMUnavailable

        self.prompts.append((system, user))
        if self.fail:
            raise LLMUnavailable("down")
        return self.responses.pop(0) if self.responses else {}


@pytest.fixture
def settings() -> Settings:
    return Settings(
        allow_private_hosts=True, http_retries=1, http_backoff_s=0.0, cache_ttl_s=0,
        feeds={"Alpha News / Business": "https://alpha.example/rss", "Beta Wire / Technology": "https://beta.example/rss"},
        database_path=":memory:",
    )


@pytest.fixture
def good_routes() -> dict:
    return {
        "https://alpha.example/rss": rss([
            ("Nvidia shares surge as AI chip demand grows", "https://alpha.example/a1?utm_source=x",
             "Investors cheer strong AI demand for chips.", "Fri, 02 Oct 2026 09:00:00 GMT"),
            ("Oil prices fall as OPEC weighs output cut", "https://alpha.example/a2",
             "Crude oil slid on demand concerns.", "Fri, 02 Oct 2026 08:00:00 GMT"),
            ("Central bank warns of inflation risks", "https://alpha.example/a3",
             "The economy faces inflation and weak growth.", "Thu, 01 Oct 2026 18:00:00 GMT"),
        ]),
        "https://beta.example/rss": rss([
            ("Nvidia shares surge as AI chip demand grows", "https://beta.example/b1",
             "AI chip demand boosts Nvidia.", "Fri, 02 Oct 2026 10:00:00 GMT"),
            ("Startup launches new AI assistant for software teams", "https://beta.example/b2",
             "A new AI tool for developers.", "Fri, 02 Oct 2026 07:00:00 GMT"),
        ]),
    }


@pytest.fixture
def make_fetcher(settings):
    def _make(routes: dict, st: Settings | None = None) -> FeedFetcher:
        return FeedFetcher(st or settings, session=FakeSession(routes))
    return _make


@pytest.fixture
def repo():
    r = SQLiteRepository(":memory:")
    r.init()
    return r


@pytest.fixture
def timeout_error():
    return requests.Timeout("slow")
