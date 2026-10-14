"""Remove duplicate stories by normalised URL and headline similarity."""
from __future__ import annotations

import re
from difflib import SequenceMatcher

from app.schemas.briefing import Article

_STOP = {"the", "a", "an", "of", "to", "in", "on", "for", "and", "as", "at", "by", "is", "are", "with"}


def _tokens(title: str) -> set[str]:
    return {t for t in re.findall(r"[a-z0-9]+", title.lower()) if t not in _STOP}


def title_similarity(a: str, b: str) -> float:
    ta, tb = _tokens(a), _tokens(b)
    jaccard = len(ta & tb) / len(ta | tb) if ta and tb else 0.0
    ratio = SequenceMatcher(None, a.lower(), b.lower()).ratio()
    return max(jaccard, ratio)


def deduplicate_detailed(
    articles: list[Article], threshold: float = 0.82
) -> tuple[list[Article], dict[str, list[Article]]]:
    """Return (unique_articles, groups) where groups maps kept.id -> duplicate articles."""
    kept: list[Article] = []
    groups: dict[str, list[Article]] = {}
    seen_urls: dict[str, Article] = {}
    for art in articles:
        if art.url in seen_urls:
            groups.setdefault(seen_urls[art.url].id, []).append(art)
            continue
        match = next((k for k in kept if title_similarity(art.title, k.title) >= threshold), None)
        if match is not None:
            groups.setdefault(match.id, []).append(art)
            continue
        seen_urls[art.url] = art
        kept.append(art)
    return kept, groups


def deduplicate(articles: list[Article], threshold: float = 0.82) -> tuple[list[Article], int]:
    """Return (unique_articles, removed_count). First-seen article wins."""
    kept, groups = deduplicate_detailed(articles, threshold)
    return kept, sum(len(v) for v in groups.values())
