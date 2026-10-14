"""Pydantic schemas shared by workflow, storage and API."""
from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator

SentimentLabel = Literal["positive", "neutral", "negative"]
ClaimKind = Literal["verified_fact", "source_attributed", "analytical_interpretation"]
Mode = Literal["deterministic_fallback", "llm"]

TOPICS = ["ai", "technology", "markets", "business", "energy", "economy"]

SENTIMENT_DISCLAIMER = (
    "Sentiment scores are analytical signals computed from headlines and summaries. "
    "They are not market forecasts or investment recommendations."
)


class Article(BaseModel):
    id: str
    title: str
    publisher: str
    url: str
    summary: str = ""
    published_at: Optional[datetime] = None
    collected_at: datetime
    feed_name: str = ""
    topics: list[str] = Field(default_factory=list)
    sentiment_score: Optional[float] = None
    sentiment_label: Optional[SentimentLabel] = None
    suspicious: bool = False


class Theme(BaseModel):
    name: str
    article_count: int
    publishers: list[str] = Field(default_factory=list)
    evidence: list[str] = Field(default_factory=list)  # article URLs
    avg_sentiment: float = 0.0
    note: str = "Theme derived from recurring terms; an analytical signal, not a forecast."


class Claim(BaseModel):
    text: str
    kind: ClaimKind
    source_urls: list[str] = Field(default_factory=list)
    publishers: list[str] = Field(default_factory=list)
    important: bool = True
    why_it_matters: str = ""
    published_at: Optional[datetime] = None


class ClaimCheck(BaseModel):
    claim: str
    status: Literal["supported", "single_source", "unsupported", "stale", "missing_date"]
    detail: str
    source_urls: list[str] = Field(default_factory=list)


class ValidationResult(BaseModel):
    passed: bool
    checks: list[ClaimCheck] = Field(default_factory=list)
    flags: list[str] = Field(default_factory=list)
    revisions: int = 0
    unsupported_removed: int = 0


class SentimentOverview(BaseModel):
    engine: str
    positive: int = 0
    neutral: int = 0
    negative: int = 0
    mean_score: float = 0.0
    disclaimer: str = SENTIMENT_DISCLAIMER


class Briefing(BaseModel):
    id: str
    generated_at: datetime
    period_start: datetime
    period_end: datetime
    topics: list[str]
    mode: Mode
    mode_label: str
    executive_summary: str
    key_developments: list[Claim] = Field(default_factory=list)
    emerging_themes: list[Theme] = Field(default_factory=list)
    sentiment: SentimentOverview
    risks: list[str] = Field(default_factory=list)
    uncertainties: list[str] = Field(default_factory=list)
    sources: list[Article] = Field(default_factory=list)
    validation: ValidationResult
    markdown: str = ""
    email_draft: str = ""
    is_sample: bool = False


class GenerateRequest(BaseModel):
    topics: list[str] = Field(default_factory=lambda: ["ai", "technology", "markets"])
    days: int = Field(default=2, ge=1, le=14)
    max_articles: int = Field(default=40, ge=5, le=100)
    use_llm: bool = False

    @field_validator("topics")
    @classmethod
    def _valid_topics(cls, v: list[str]) -> list[str]:
        cleaned = [t.strip().lower() for t in v]
        bad = [t for t in cleaned if t not in TOPICS]
        if not cleaned or bad:
            raise ValueError(f"topics must be a non-empty subset of {TOPICS}")
        return sorted(set(cleaned))


class StageStatus(BaseModel):
    name: str
    state: Literal["pending", "running", "completed", "failed", "skipped"] = "pending"
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    detail: str = ""
    error: Optional[str] = None


class WorkflowStatus(BaseModel):
    run_id: str
    state: Literal["idle", "running", "completed", "failed"] = "idle"
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    mode: Optional[str] = None
    stages: list[StageStatus] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    briefing_id: Optional[str] = None


class ArticlePage(BaseModel):
    total: int
    page: int
    page_size: int
    items: list[Article]


class Analytics(BaseModel):
    article_count: int
    topic_distribution: dict[str, int]
    sentiment_distribution: dict[str, int]
    mean_sentiment: float
    source_coverage: dict[str, int]
    disclaimer: str = SENTIMENT_DISCLAIMER
