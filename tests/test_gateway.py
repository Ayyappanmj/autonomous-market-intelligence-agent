import httpx
import pytest
from fastapi.testclient import TestClient

from gateway import create_gateway_app


class Recorder:
    def __init__(self, fail: bool = False):
        self.requests, self.fail = [], fail

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if self.fail:
            raise httpx.ConnectError("refused")
        return httpx.Response(200, content=b"<html>dashboard</html>",
                              headers=[("content-type", "text/html"), ("set-cookie", "a=1"),
                                       ("set-cookie", "b=2"), ("x-up", "1")])


@pytest.fixture
def rec():
    return Recorder()


def make(settings, repo, make_fetcher, rec, **kw):
    client = httpx.AsyncClient(transport=httpx.MockTransport(rec))
    return TestClient(create_gateway_app(settings, repo, make_fetcher({}), http_client=client, **kw))


def test_api_routes_are_served_in_process(settings, repo, make_fetcher, rec):
    c = make(settings, repo, make_fetcher, rec)
    assert c.get("/health").json()["status"] == "ok"
    assert c.get("/docs").status_code == 200 and c.get("/openapi.json").status_code == 200
    assert c.get("/api/v1/briefings/latest").status_code == 404
    assert rec.requests == []  # none of the API calls went to the dashboard upstream


def test_root_and_assets_proxy_to_dashboard(settings, repo, make_fetcher, rec):
    c = make(settings, repo, make_fetcher, rec)
    r = c.get("/?x=1")
    assert r.status_code == 200 and b"dashboard" in r.content
    assert r.headers["x-up"] == "1"
    assert [h for h in r.headers.get_list("set-cookie")] == ["a=1", "b=2"]
    up = rec.requests[0]
    assert str(up.url) == "http://127.0.0.1:8501/?x=1" and up.headers["host"] == "testserver"
    c.get("/_stcore/health")
    assert rec.requests[1].url.path == "/_stcore/health"


def test_path_tricks_cannot_reach_other_hosts(settings, repo, make_fetcher, rec):
    c = make(settings, repo, make_fetcher, rec)
    for path in ("//evil.example/x", "/%2F%2Fevil.example/x", "/..//evil.example"):
        c.get(path)
    assert rec.requests and all(r.url.host == "127.0.0.1" and r.url.port == 8501 for r in rec.requests)


def test_unknown_api_paths_return_json_404_not_dashboard(settings, repo, make_fetcher, rec):
    c = make(settings, repo, make_fetcher, rec)
    r = c.get("/api/v1/nope")
    assert r.status_code == 404 and r.json()["detail"] and rec.requests == []


def test_upstream_down_returns_safe_502(settings, repo, make_fetcher):
    c = make(settings, repo, make_fetcher, Recorder(fail=True))
    r = c.get("/")
    assert r.status_code == 502 and "refused" not in r.text and "127.0.0.1" not in r.text
    assert c.get("/health").status_code == 200  # API keeps working when the dashboard is down


def test_post_body_and_hop_headers(settings, repo, make_fetcher, rec):
    c = make(settings, repo, make_fetcher, rec)
    c.post("/_stcore/x", content=b"hello", headers={"connection": "keep-alive", "x-keep": "1"})
    up = rec.requests[0]
    assert up.content == b"hello" and up.headers["x-keep"] == "1"


class FakeWS:
    subprotocol = None

    def __init__(self):
        import asyncio
        self.q = asyncio.Queue()

    async def send(self, message):
        await self.q.put(("echo:" + message) if isinstance(message, str) else b"echo:" + message)

    def __aiter__(self):
        return self

    async def __anext__(self):
        return await self.q.get()


class FakeConnector:
    def __call__(self, url, **kwargs):
        self.url, self.kwargs = url, kwargs
        return self

    async def __aenter__(self):
        return FakeWS()

    async def __aexit__(self, *exc):
        return False


def test_websocket_is_relayed_both_ways(settings, repo, make_fetcher, rec):
    conn = FakeConnector()
    c = make(settings, repo, make_fetcher, rec, ws_connect=conn)
    with c.websocket_connect("/_stcore/stream") as ws:
        ws.send_text("hi")
        assert ws.receive_text() == "echo:hi"
        ws.send_bytes(b"\x01")
        assert ws.receive_bytes() == b"echo:\x01"
    assert conn.url == "ws://127.0.0.1:8501/_stcore/stream"


def test_websocket_upstream_failure_closes_cleanly(settings, repo, make_fetcher, rec):
    class Boom(FakeConnector):
        async def __aenter__(self):
            raise OSError("down")

    c = make(settings, repo, make_fetcher, rec, ws_connect=Boom())
    with pytest.raises(Exception):
        with c.websocket_connect("/_stcore/stream"):
            pass
