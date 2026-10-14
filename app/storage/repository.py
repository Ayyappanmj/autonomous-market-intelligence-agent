"""Repository layer. SQLite implementation; swap in PostgreSQL by implementing `Repository`."""
from __future__ import annotations

import sqlite3
import threading
from abc import ABC, abstractmethod
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterator, Optional

from app.schemas.briefing import (
    Analytics, Article, ArticlePage, Briefing, SENTIMENT_DISCLAIMER, WorkflowStatus,
)
from app.utils.logging import get_logger

log = get_logger(__name__)
KEEP_BRIEFINGS = 50
KEEP_ARTICLE_DAYS = 14


class Repository(ABC):
    @abstractmethod
    def init(self) -> None: ...
    @abstractmethod
    def save_briefing(self, briefing: Briefing) -> None: ...
    @abstractmethod
    def latest_briefing(self) -> Optional[Briefing]: ...
    @abstractmethod
    def get_briefing(self, briefing_id: str) -> Optional[Briefing]: ...
    @abstractmethod
    def list_briefings(self, limit: int = 20) -> list[dict]: ...
    @abstractmethod
    def upsert_articles(self, articles: list[Article]) -> None: ...
    @abstractmethod
    def list_articles(self, topics: Optional[list[str]], page: int, page_size: int) -> ArticlePage: ...
    @abstractmethod
    def analytics(self) -> Analytics: ...
    @abstractmethod
    def save_status(self, status: WorkflowStatus) -> None: ...
    @abstractmethod
    def latest_status(self) -> Optional[WorkflowStatus]: ...


class SQLiteRepository(Repository):
    def __init__(self, path: str):
        self.path = path
        self._lock = threading.Lock()
        if path != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._shared: Optional[sqlite3.Connection] = None
        if path == ":memory:":  # one shared connection so tests see the same DB
            self._shared = sqlite3.connect(path, check_same_thread=False)

    @contextmanager
    def _conn(self) -> Iterator[sqlite3.Connection]:
        with self._lock:
            conn = self._shared or sqlite3.connect(self.path, timeout=10)
            try:
                yield conn
                conn.commit()
            finally:
                if self._shared is None:
                    conn.close()

    def init(self) -> None:  # idempotent
        with self._conn() as c:
            c.executescript(
                """
                CREATE TABLE IF NOT EXISTS briefings (
                    id TEXT PRIMARY KEY, generated_at TEXT NOT NULL, payload TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS articles (
                    id TEXT PRIMARY KEY, collected_at TEXT NOT NULL,
                    published_at TEXT, payload TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS workflow_status (
                    run_id TEXT PRIMARY KEY, updated_at TEXT NOT NULL, payload TEXT NOT NULL);
                """
            )

    # ---- briefings
    def save_briefing(self, briefing: Briefing) -> None:
        with self._conn() as c:
            c.execute(
                "INSERT OR REPLACE INTO briefings (id, generated_at, payload) VALUES (?,?,?)",
                (briefing.id, briefing.generated_at.isoformat(), briefing.model_dump_json()),
            )
            c.execute(
                "DELETE FROM briefings WHERE id NOT IN "
                "(SELECT id FROM briefings ORDER BY generated_at DESC LIMIT ?)",
                (KEEP_BRIEFINGS,),
            )

    def _load_briefing(self, payload: str) -> Optional[Briefing]:
        try:
            return Briefing.model_validate_json(payload)
        except Exception:  # corrupt or schema-drifted record: skip safely
            log.warning("skipping corrupt briefing record")
            return None

    def latest_briefing(self) -> Optional[Briefing]:
        with self._conn() as c:
            rows = c.execute("SELECT payload FROM briefings ORDER BY generated_at DESC LIMIT 10").fetchall()
        for (payload,) in rows:
            b = self._load_briefing(payload)
            if b:
                return b
        return None

    def get_briefing(self, briefing_id: str) -> Optional[Briefing]:
        with self._conn() as c:
            row = c.execute("SELECT payload FROM briefings WHERE id=?", (briefing_id,)).fetchone()
        return self._load_briefing(row[0]) if row else None

    def list_briefings(self, limit: int = 20) -> list[dict]:
        with self._conn() as c:
            rows = c.execute(
                "SELECT payload FROM briefings ORDER BY generated_at DESC LIMIT ?", (limit,)
            ).fetchall()
        out = []
        for (payload,) in rows:
            b = self._load_briefing(payload)
            if b:
                out.append(
                    {
                        "id": b.id,
                        "generated_at": b.generated_at.isoformat(),
                        "topics": b.topics,
                        "mode": b.mode,
                        "article_count": len(b.sources),
                        "is_sample": b.is_sample,
                    }
                )
        return out

    # ---- articles
    def upsert_articles(self, articles: list[Article]) -> None:
        cutoff = (datetime.now(timezone.utc) - timedelta(days=KEEP_ARTICLE_DAYS)).isoformat()
        with self._conn() as c:
            for a in articles:
                c.execute(
                    "INSERT OR REPLACE INTO articles (id, collected_at, published_at, payload) VALUES (?,?,?,?)",
                    (a.id, a.collected_at.isoformat(), a.published_at.isoformat() if a.published_at else None,
                     a.model_dump_json()),
                )
            c.execute("DELETE FROM articles WHERE collected_at < ?", (cutoff,))

    def _all_articles(self) -> list[Article]:
        with self._conn() as c:
            rows = c.execute(
                "SELECT payload FROM articles ORDER BY COALESCE(published_at, collected_at) DESC"
            ).fetchall()
        out = []
        for (payload,) in rows:
            try:
                out.append(Article.model_validate_json(payload))
            except Exception:
                log.warning("skipping corrupt article record")
        return out

    def list_articles(self, topics: Optional[list[str]], page: int, page_size: int) -> ArticlePage:
        items = self._all_articles()
        if topics:
            items = [a for a in items if set(a.topics) & set(topics)]
        start = (page - 1) * page_size
        return ArticlePage(total=len(items), page=page, page_size=page_size, items=items[start:start + page_size])

    def analytics(self) -> Analytics:
        items = self._all_articles()
        topics: dict[str, int] = {}
        sentiments = {"positive": 0, "neutral": 0, "negative": 0}
        sources: dict[str, int] = {}
        scores = []
        for a in items:
            for t in a.topics:
                topics[t] = topics.get(t, 0) + 1
            if a.sentiment_label:
                sentiments[a.sentiment_label] += 1
            if a.sentiment_score is not None:
                scores.append(a.sentiment_score)
            sources[a.publisher] = sources.get(a.publisher, 0) + 1
        return Analytics(
            article_count=len(items),
            topic_distribution=dict(sorted(topics.items(), key=lambda kv: -kv[1])),
            sentiment_distribution=sentiments,
            mean_sentiment=round(sum(scores) / len(scores), 3) if scores else 0.0,
            source_coverage=dict(sorted(sources.items(), key=lambda kv: -kv[1])),
            disclaimer=SENTIMENT_DISCLAIMER,
        )

    # ---- workflow status
    def save_status(self, status: WorkflowStatus) -> None:
        with self._conn() as c:
            c.execute(
                "INSERT OR REPLACE INTO workflow_status (run_id, updated_at, payload) VALUES (?,?,?)",
                (status.run_id, datetime.now(timezone.utc).isoformat(), status.model_dump_json()),
            )
            c.execute(
                "DELETE FROM workflow_status WHERE run_id NOT IN "
                "(SELECT run_id FROM workflow_status ORDER BY updated_at DESC LIMIT 20)"
            )

    def latest_status(self) -> Optional[WorkflowStatus]:
        with self._conn() as c:
            row = c.execute("SELECT payload FROM workflow_status ORDER BY updated_at DESC LIMIT 1").fetchone()
        if not row:
            return None
        try:
            return WorkflowStatus.model_validate_json(row[0])
        except Exception:
            return None
