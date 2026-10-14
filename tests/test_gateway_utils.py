from app.gateway_utils import extract_client_ip, filter_headers, upstream_url


def test_filter_headers_drops_hop_by_hop_keeps_duplicates():
    out = filter_headers([("Connection", "x"), ("Set-Cookie", "a=1"), ("set-cookie", "b=2"),
                          ("Transfer-Encoding", "chunked"), ("Host", "h"), ("X-Ok", "1")], drop=("host",))
    assert out == [("Set-Cookie", "a=1"), ("set-cookie", "b=2"), ("X-Ok", "1")]


def test_upstream_url_cannot_change_host():
    base = "http://127.0.0.1:8501"
    assert upstream_url(base, "static/a.js", "v=1") == "http://127.0.0.1:8501/static/a.js?v=1"
    assert upstream_url(base, "/evil.example/x") == "http://127.0.0.1:8501/evil.example/x"
    assert upstream_url(base, "//evil.example/x") == "http://127.0.0.1:8501/evil.example/x"
    assert upstream_url(base, "\\\\evil.example\\x") == "http://127.0.0.1:8501/evil.example/x"
    assert upstream_url(base + "/", "") == "http://127.0.0.1:8501/"


def test_client_ip_ignores_forged_header_unless_trusted():
    assert extract_client_ip("10.0.0.1", "6.6.6.6", trust_proxy=False) == "10.0.0.1"
    assert extract_client_ip(None, None, False) == "unknown"
    # client forged "1.1.1.1"; trusted proxy appended the real address 9.9.9.9
    assert extract_client_ip("10.0.0.1", "1.1.1.1, 9.9.9.9", trust_proxy=True, hops=1) == "9.9.9.9"
    assert extract_client_ip("10.0.0.1", "9.9.9.9, 172.16.0.1", trust_proxy=True, hops=2) == "9.9.9.9"
    assert extract_client_ip("10.0.0.1", "9.9.9.9", trust_proxy=True, hops=5) == "9.9.9.9"
    assert extract_client_ip("10.0.0.1", None, trust_proxy=True) == "10.0.0.1"
