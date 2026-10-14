"""Agent 1 - News Research Agent."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta

from app.config import Settings
from app.ingestion.normalizer import normalize_entry
from app.ingestion.rss_reader import FeedFetcher
from app.schemas.briefing import Article


@dataclass
class ResearchOutput:
    articles: list[Article] = field(default_factory=list)
    feed_report: list[dict] = field(default_factory=list)
    rejected: int = 0
    period_start: datetime | None = None
    period_end: datetime | None = None

    @property
    def errors(self) -> list[str]:
        return [f"{f['feed']}: {f['error']}" for f in self.feed_report if f.get("error")]


class ResearchAgent:
    name = "News Research Agent"

    def __init__(self, settings: Settings, fetcher: FeedFetcher):
        self.settings = settings
        self.fetcher = fetcher

    def run(self, days: int, now: datetime, feeds: dict[str, str] | None = None) -> ResearchOutput:
        out = ResearchOutput(period_start=now - timedelta(days=days), period_end=now)
        for result in self.fetcher.fetch_all(feeds or self.settings.feeds):
            out.feed_report.append(
                {"feed": result.feed_name, "entries": len(result.entries), "error": result.error,
                 "cached": result.from_cache}
            )
            for raw in result.entries:
                art = normalize_entry(raw, result.feed_name, now)
                if art is None:
                    out.rejected += 1
                    continue
                # keep undated items (verification will flag them); drop items older than the period
                if art.published_at is not None and art.published_at < out.period_start:
                    continue
                out.articles.append(art)
        out.articles.sort(
            key=lambda a: a.published_at.timestamp() if a.published_at else 0.0, reverse=True
        )
        return out
