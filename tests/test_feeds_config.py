import json

from app.config import VALID_TOPICS, get_settings, load_feeds_file, parse_feed_config, select_feeds
from app.schemas.briefing import TOPICS


def test_topic_lists_stay_in_sync():
    assert list(VALID_TOPICS) == TOPICS


def test_shipped_feeds_file_is_valid():
    feeds, topics = load_feeds_file("config/feeds.json")
    assert len(feeds) >= 10 and all(u.startswith("https://") for u in feeds.values())
    assert set(topics) <= set(feeds) and all(set(t) <= set(VALID_TOPICS) for t in topics.values())
    assert all(any(t in hint for hint in topics.values()) for t in VALID_TOPICS)  # every topic has a feed


def test_parse_skips_invalid_duplicate_and_disabled_entries():
    data = {"feeds": [
        {"name": "A", "url": "https://a.example/rss", "topics": ["ai", "bogus"]},
        {"name": "A", "url": "https://other.example/rss"},          # duplicate name
        {"name": "B", "url": "https://a.example/rss"},              # duplicate url
        {"name": "C", "url": "ftp://c.example/rss"},                # bad scheme
        {"name": "", "url": "https://d.example/rss"},               # empty name
        {"name": "E", "url": "https://e.example/rss", "enabled": False},
        {"name": "F", "url": "https://f.example/rss"},
        "junk", 7, {"name": 3, "url": 4},
    ]}
    feeds, topics = parse_feed_config(data)
    assert feeds == {"A": "https://a.example/rss", "F": "https://f.example/rss"}
    assert topics == {"A": ("ai",)}


def test_parse_handles_garbage_and_missing_file(tmp_path):
    assert parse_feed_config("nope") == ({}, {}) and parse_feed_config({"feeds": "x"}) == ({}, {})
    bad = tmp_path / "bad.json"
    bad.write_text("{not json")
    assert load_feeds_file(str(bad)) == ({}, {}) and load_feeds_file(str(tmp_path / "missing.json")) == ({}, {})


def test_select_feeds_filters_ranks_and_limits():
    feeds = {"Tech": "u1", "Energy": "u2", "Both": "u3", "Untagged": "u4"}
    hints = {"Tech": ("technology",), "Energy": ("energy",), "Both": ("technology", "energy")}
    assert list(select_feeds(feeds, hints, ["energy"], 10)) == ["Energy", "Both", "Untagged"]
    assert list(select_feeds(feeds, hints, ["technology", "energy"], 10))[0] == "Both"
    assert len(select_feeds(feeds, hints, ["energy"], 1)) == 1
    assert len(select_feeds(feeds, hints, [], 10)) == 4  # no topic filter -> all feeds


def test_get_settings_prefers_env_feeds_then_file(tmp_path, monkeypatch):
    f = tmp_path / "f.json"
    f.write_text(json.dumps({"feeds": [{"name": "Only", "url": "https://only.example/rss", "topics": ["energy"]}]}))
    get_settings.cache_clear()
    monkeypatch.setenv("FEEDS_FILE", str(f))
    assert get_settings().feeds == {"Only": "https://only.example/rss"}
    get_settings.cache_clear()
    monkeypatch.setenv("FEEDS", "X|https://x.example/rss")
    assert get_settings().feeds == {"X": "https://x.example/rss"}
    get_settings.cache_clear()
    monkeypatch.delenv("FEEDS"); monkeypatch.setenv("FEEDS_FILE", str(tmp_path / "nope.json"))
    assert get_settings().feeds  # falls back to built-in defaults
    get_settings.cache_clear()
