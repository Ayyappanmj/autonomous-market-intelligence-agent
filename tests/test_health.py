from fastapi.testclient import TestClient

from app.main import create_app


def test_health_ok(settings, repo, make_fetcher):
    client = TestClient(create_app(settings, repo, make_fetcher({})))
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok" and body["version"] and body["llm_configured"] is False


def test_root_and_docs(settings, repo, make_fetcher):
    client = TestClient(create_app(settings, repo, make_fetcher({})))
    assert client.get("/").json()["docs"] == "/docs"
    assert client.get("/docs").status_code == 200
