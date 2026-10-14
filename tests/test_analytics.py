from app.analytics.sentiment import analyze, score_text
from app.analytics.trends import categorize, extract_themes
from app.ingestion.normalizer import normalize_entry
from tests.conftest import NOW


def art(title, summary="", url="https://x.example/1", pub="P / X"):
    a = normalize_entry({"title": title, "link": url, "summary": summary}, pub, NOW)
    a.sentiment_score, a.sentiment_label = analyze(f"{title} {summary}")
    return a


def test_sentiment_polarity():
    assert analyze("Stocks surge as profits beat forecasts")[1] == "positive"
    assert analyze("Shares plunge amid recession fears and layoffs")[1] == "negative"
    assert analyze("Committee meets on Tuesday")[1] == "neutral"


def test_negation_and_bounds():
    assert score_text("profits not strong") < score_text("profits strong")
    for t in ("surge " * 50, "crash " * 50, ""):
        assert -1 <= score_text(t) <= 1


def test_categorize_topics():
    a = art("Nvidia AI chip demand lifts stocks", "Oil and OPEC unrelated")
    assert {"ai", "markets", "energy"} <= set(categorize(a))
    assert categorize(a, allowed=["energy"]) == ["energy"]


def test_themes_require_recurrence_and_cite_evidence():
    arts = [art("Tariff talks rattle trade partners", url="https://a.example/1", pub="A / X"),
            art("New tariff deal eases trade tension", url="https://b.example/2", pub="B / X"),
            art("Unrelated gardening story today", url="https://c.example/3", pub="C / X")]
    themes = extract_themes(arts)
    assert themes and all(t.article_count >= 2 and t.evidence for t in themes)
    assert all("gardening" not in t.name for t in themes)
    assert extract_themes(arts[:1]) == []
