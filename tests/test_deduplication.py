from app.ingestion.deduplicator import deduplicate, deduplicate_detailed, title_similarity
from app.ingestion.normalizer import normalize_entry
from tests.conftest import NOW


def art(title, url):
    return normalize_entry({"title": title, "link": url}, "Pub / X", NOW)


def test_same_url_with_tracking_params_deduped():
    a, b = art("Markets rally on jobs data", "https://x.example/a?utm_source=1"), art("Different headline entirely", "https://www.x.example/a/")
    unique, removed = deduplicate([a, b])
    assert len(unique) == 1 and removed == 1


def test_similar_headlines_deduped_and_distinct_kept():
    arts = [art("Nvidia shares surge as AI chip demand grows", "https://a.example/1"),
            art("Nvidia shares surge as AI chip demand grows!", "https://b.example/2"),
            art("Oil falls as OPEC weighs output cut", "https://c.example/3")]
    unique, groups = deduplicate_detailed(arts)
    assert [u.url for u in unique] == ["https://a.example/1", "https://c.example/3"]
    assert len(groups[unique[0].id]) == 1


def test_similarity_bounds():
    assert title_similarity("same title here", "same title here") == 1.0
    assert title_similarity("apples oranges", "quantum computing breakthrough") < 0.4
