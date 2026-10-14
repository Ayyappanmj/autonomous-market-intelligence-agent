import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


@pytest.fixture
def client(settings, repo, make_fetcher, good_routes):
    return TestClient(create_app(settings, repo, make_fetcher(good_routes)))


BODY = {"topics": ["ai", "markets", "technology", "energy", "economy"], "days": 14}


def test_generate_then_read_everything(client):
    r = client.post("/api/v1/briefings/generate", json=BODY)
    assert r.status_code == 200, r.text
    b = r.json()
    assert b["mode"] == "deterministic_fallback" and b["markdown"] and b["validation"]["passed"]
    assert client.get("/api/v1/briefings/latest").json()["id"] == b["id"]
    assert client.get(f"/api/v1/briefings/{b['id']}").status_code == 200
    assert client.get("/api/v1/briefings/history").json()["items"][0]["id"] == b["id"]
    news = client.get("/api/v1/news", params={"topic": "ai", "page_size": 2}).json()
    assert news["total"] >= 1 and len(news["items"]) <= 2
    an = client.get("/api/v1/analytics").json()
    assert an["article_count"] > 0 and "not market forecasts" in an["disclaimer"]
    st = client.get("/api/v1/agents/status").json()
    assert st["state"] == "completed" and len(st["stages"]) == 6


def test_empty_state_responses(client):
    assert client.get("/api/v1/briefings/latest").status_code == 404
    assert client.get("/api/v1/briefings/history").json() == {"items": []}
    assert client.get("/api/v1/news").json()["total"] == 0
    assert client.get("/api/v1/agents/status").json()["state"] == "idle"
    assert client.get("/api/v1/briefings/doesnotexist").status_code == 404


@pytest.mark.parametrize("body", [{"topics": ["crypto-moon"]}, {"topics": []}, {"days": 999}, {"max_articles": 1}, {"days": "x"}])
def test_invalid_requests_return_422(client, body):
    r = client.post("/api/v1/briefings/generate", json=body)
    assert r.status_code == 422 and r.json()["detail"] == "Invalid request."


def test_invalid_query_params(client):
    assert client.get("/api/v1/news", params={"topic": "nope"}).status_code == 422
    assert client.get("/api/v1/news", params={"page_size": 1000}).status_code == 422
    assert client.get("/api/v1/briefings/bad!id").status_code == 422


def test_oversized_body_rejected(client):
    r = client.post("/api/v1/briefings/generate", content=b"x" * 20_000, headers={"content-type": "application/json"})
    assert r.status_code == 413


def test_busy_returns_409(client):
    wf = client.app.state.workflow
    wf._lock.acquire()
    try:
        assert client.post("/api/v1/briefings/generate", json=BODY).status_code == 409
    finally:
        wf._lock.release()


def test_no_articles_returns_503_without_internals(settings, repo, make_fetcher):
    c = TestClient(create_app(settings, repo, make_fetcher({})))
    r = c.post("/api/v1/briefings/generate", json=BODY)
    assert r.status_code == 503 and "Traceback" not in r.text and "alpha.example" not in r.text


def test_unexpected_error_is_sanitised(client, monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("db password=hunter2")
    monkeypatch.setattr(client.app.state.repo, "latest_briefing", boom)
    c = TestClient(client.app, raise_server_exceptions=False)
    r = c.get("/api/v1/briefings/latest")
    assert r.status_code == 500 and "hunter2" not in r.text and r.json()["detail"] == "Internal server error."


def test_rate_limiting(settings, repo, make_fetcher, good_routes):
    st = Settings(**{**settings.__dict__, "generate_rate_limit_per_min": 2, "rate_limit_per_min": 3})
    c = TestClient(create_app(st, repo, make_fetcher(good_routes)))
    codes = [c.get("/api/v1/analytics").status_code for _ in range(5)]
    assert codes[:3] == [200] * 3 and codes[3] == 429
    codes = [c.post("/api/v1/briefings/generate", json={"topics": ["zzz"]}).status_code for _ in range(4)]
    assert 429 in codes


def test_api_key_never_exposed(settings, repo, make_fetcher):
    st = Settings(**{**settings.__dict__, "llm_provider": "openai_compatible", "llm_api_key": "sk-SECRET123"})
    c = TestClient(create_app(st, repo, make_fetcher({})))
    for path in ("/health", "/", "/openapi.json"):
        assert "sk-SECRET123" not in c.get(path).text
    assert c.get("/health").json()["llm_configured"] is True


def test_feeds_endpoint_lists_sources(client):
    body = client.get("/api/v1/feeds").json()
    assert {f["name"] for f in body["items"]} == {"Alpha News / Business", "Beta Wire / Technology"}
    assert body["max_feeds_per_run"] >= 1


def test_forwarded_for_only_trusted_when_configured(settings, repo, make_fetcher, good_routes):
    base = {**settings.__dict__, "rate_limit_per_min": 2}
    for trust, expect_429 in ((False, True), (True, False)):
        st = Settings(**{**base, "trust_proxy": trust})
        c = TestClient(create_app(st, repo, make_fetcher(good_routes)))
        codes = [c.get("/api/v1/analytics", headers={"x-forwarded-for": f"9.9.9.{i}"}).status_code for i in range(4)]
        assert (429 in codes) is expect_429
