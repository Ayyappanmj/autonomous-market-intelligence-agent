"""Deterministic topic categorisation and recurring-theme detection."""
from __future__ import annotations

import re
from collections import Counter, defaultdict
from statistics import mean

from app.schemas.briefing import Article, Theme

TOPIC_KEYWORDS: dict[str, tuple[str, ...]] = {
    "ai": ("ai", "artificial intelligence", "machine learning", "chatbot", "openai", "anthropic", "gemini",
           "llm", "generative", "nvidia", "neural", "copilot", "deepmind", "algorithm"),
    "technology": ("tech", "software", "chip", "chips", "semiconductor", "cloud", "cyber", "apple", "google",
                   "microsoft", "meta", "amazon", "startup", "app", "smartphone", "data centre", "data center"),
    "markets": ("stock", "stocks", "shares", "market", "markets", "wall street", "nasdaq", "dow", "s&p",
                "bond", "bonds", "yield", "index", "investors", "equities", "ftse", "nikkei", "crypto", "bitcoin"),
    "business": ("company", "ceo", "merger", "acquisition", "deal", "earnings", "revenue", "profit", "retail",
                 "layoffs", "firm", "business", "brand", "bank", "airline", "automaker"),
    "energy": ("oil", "gas", "opec", "energy", "solar", "wind", "nuclear", "renewable", "crude", "power grid",
               "electricity", "battery", "lng", "fuel"),
    "economy": ("economy", "economic", "inflation", "gdp", "fed", "central bank", "interest rate", "rates",
                "tariff", "tariffs", "unemployment", "jobs", "recession", "trade", "ecb", "treasury", "growth"),
}

_STOP = set(
    "the a an and or but of to in on for with as at by from is are was were be been it its this that these those "
    "has have had will would could should may might can after before over under into out up down new says say said "
    "more most less than about amid against how why what when who which their his her our your you they we "
    "year years week weeks day days today first last next also not no just now one two us uk".split()
)
_WORD = re.compile(r"[a-z][a-z0-9&'-]{2,}")


def categorize(article: Article, allowed: list[str] | None = None) -> list[str]:
    text = f" {article.title} {article.summary} ".lower()
    found = []
    for topic, kws in TOPIC_KEYWORDS.items():
        if allowed and topic not in allowed:
            continue
        for kw in kws:
            if re.search(rf"(?<![a-z0-9]){re.escape(kw)}(?![a-z0-9])", text):
                found.append(topic)
                break
    return found


def _terms(article: Article) -> set[str]:
    words = [w for w in _WORD.findall(f"{article.title} {article.summary}".lower()) if w not in _STOP]
    unigrams = set(words)
    bigrams = {f"{a} {b}" for a, b in zip(words, words[1:])}
    return unigrams | bigrams


def extract_themes(articles: list[Article], min_articles: int = 2, max_themes: int = 6) -> list[Theme]:
    """Recurring terms appearing in >= min_articles from the same run; evidence = article URLs."""
    df: Counter[str] = Counter()
    where: dict[str, list[Article]] = defaultdict(list)
    for art in articles:
        for term in _terms(art):
            df[term] += 1
            where[term].append(art)
    candidates = [t for t, c in df.items() if c >= min_articles]
    # prefer bigrams, then higher frequency, then alphabetical (deterministic)
    candidates.sort(key=lambda t: (-df[t] * (1.5 if " " in t else 1.0), -len(t), t))
    themes: list[Theme] = []
    used_articles: set[str] = set()
    used_words: set[str] = set()
    for term in candidates:
        words = set(term.split())
        if words & used_words:
            continue
        arts = where[term]
        ids = {a.id for a in arts}
        if len(ids - used_articles) < 1 and len(themes) >= 2:
            continue
        scores = [a.sentiment_score for a in arts if a.sentiment_score is not None]
        themes.append(
            Theme(
                name=term,
                article_count=len(arts),
                publishers=sorted({a.publisher for a in arts}),
                evidence=[a.url for a in arts][:5],
                avg_sentiment=round(mean(scores), 3) if scores else 0.0,
            )
        )
        used_articles |= ids
        used_words |= words
        if len(themes) >= max_themes:
            break
    return themes
