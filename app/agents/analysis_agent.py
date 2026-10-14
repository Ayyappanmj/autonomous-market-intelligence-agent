"""Agent 2 - Market Trend and Sentiment Analyst."""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from typing import Optional

from app.agents.llm import LLMClient, LLMUnavailable, SYSTEM_PROMPT, output_is_grounded, wrap_untrusted
from app.analytics.sentiment import ENGINE_NAME, analyze
from app.analytics.trends import categorize, extract_themes
from app.config import Settings
from app.schemas.briefing import Article, SentimentOverview, Theme


@dataclass
class AnalysisOutput:
    articles: list[Article] = field(default_factory=list)
    themes: list[Theme] = field(default_factory=list)
    sentiment: SentimentOverview = field(default_factory=lambda: SentimentOverview(engine=ENGINE_NAME))
    topic_counts: dict[str, int] = field(default_factory=dict)
    llm_notes: dict[str, str] = field(default_factory=dict)  # theme -> interpretation (speculative)
    llm_used: bool = False
    llm_error: Optional[str] = None


class AnalysisAgent:
    name = "Market Trend and Sentiment Analyst"

    def __init__(self, settings: Settings, llm: Optional[LLMClient] = None):
        self.settings = settings
        self.llm = llm

    def run(self, articles: list[Article], topics: list[str]) -> AnalysisOutput:
        out = AnalysisOutput()
        scored: list[Article] = []
        for art in articles:
            art.topics = categorize(art, topics or None)
            if topics and not art.topics:
                continue  # outside the requested topics
            art.sentiment_score, art.sentiment_label = analyze(f"{art.title}. {art.summary}")
            scored.append(art)
        scored = scored[: self.settings.max_articles_per_run]
        out.articles = scored
        out.topic_counts = dict(Counter(t for a in scored for t in a.topics).most_common())
        labels = Counter(a.sentiment_label for a in scored)
        scores = [a.sentiment_score for a in scored if a.sentiment_score is not None]
        out.sentiment = SentimentOverview(
            engine=ENGINE_NAME,
            positive=labels.get("positive", 0),
            neutral=labels.get("neutral", 0),
            negative=labels.get("negative", 0),
            mean_score=round(sum(scores) / len(scores), 3) if scores else 0.0,
        )
        out.themes = extract_themes([a for a in scored if not a.suspicious])
        if self.llm and out.themes:
            self._llm_interpret(out, scored)
        return out

    def _llm_interpret(self, out: AnalysisOutput, articles: list[Article]) -> None:
        safe = [a for a in articles if not a.suspicious][: self.settings.llm_max_input_articles]
        lines = [f"[{a.publisher}] {a.title}" for a in safe]
        corpus = " ".join(lines + [a.summary for a in safe])
        theme_names = [t.name for t in out.themes]
        user = (
            f"Themes detected by a deterministic algorithm: {theme_names}.\n"
            "For each theme write ONE cautious sentence explaining what the headlines suggest, phrased as "
            'interpretation (e.g. "may indicate"). Return JSON: {"notes": {"<theme>": "<sentence>"}}.\n'
            + wrap_untrusted(lines)
        )
        try:
            data = self.llm.complete_json(SYSTEM_PROMPT, user)  # type: ignore[union-attr]
            notes = data.get("notes", {})
            for theme, text in notes.items():
                if theme in theme_names and isinstance(text, str) and output_is_grounded(text, corpus):
                    out.llm_notes[theme] = text.strip()[:300]
            out.llm_used = bool(out.llm_notes)  # label LLM mode only if its output was accepted
        except LLMUnavailable:
            out.llm_error = "LLM unavailable; deterministic analysis used"
