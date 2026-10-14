from datetime import date

import pytest
import requests

from app.agents import llm as llm_mod
from app.agents.llm import CallBudget, LLMUnavailable, OpenAICompatibleClient, build_llm_client
from app.config import GEMINI_BASE_URL, Settings, get_settings


class Resp:
    def __init__(self, status=200, content='{"ok": true}', headers=None):
        self.status_code, self.headers, self._content = status, headers or {}, content

    def json(self):
        return {"choices": [{"message": {"content": self._content}}]}


class FakePost:
    def __init__(self, outcomes):
        self.outcomes, self.calls = list(outcomes), []

    def __call__(self, url, **kwargs):
        self.calls.append((url, kwargs))
        out = self.outcomes.pop(0)
        if isinstance(out, Exception):
            raise out
        return out


def client(monkeypatch, outcomes, retries=2, budget=None):
    post = FakePost(outcomes)
    monkeypatch.setattr(llm_mod.requests, "post", post)
    sleeps = []
    c = OpenAICompatibleClient("https://x.example/v1", "m", "sk-SECRET", 5, retries,
                               budget or CallBudget(50, 0.0), sleep=sleeps.append)
    return c, post, sleeps


def test_success_sends_bearer_key_and_parses_fenced_json(monkeypatch):
    c, post, _ = client(monkeypatch, [Resp(content='```json\n{"summary": "hi"}\n```')])
    assert c.complete_json("sys", "usr") == {"summary": "hi"}
    url, kw = post.calls[0]
    assert url == "https://x.example/v1/chat/completions" and kw["headers"]["Authorization"] == "Bearer sk-SECRET"
    assert kw["json"]["messages"][0]["role"] == "system" and kw["json"]["messages"][1]["content"] == "usr"


def test_json_embedded_in_prose_is_extracted(monkeypatch):
    c, _, _ = client(monkeypatch, [Resp(content='Sure! {"a": 1} hope that helps')])
    assert c.complete_json("s", "u") == {"a": 1}


def test_429_is_retried_honouring_retry_after(monkeypatch):
    c, post, sleeps = client(monkeypatch, [Resp(429, headers={"Retry-After": "3"}), Resp(200)])
    assert c.complete_json("s", "u") == {"ok": True}
    assert len(post.calls) == 2 and sleeps == [3.0]


def test_retry_after_is_capped_and_retries_are_bounded(monkeypatch):
    c, post, sleeps = client(monkeypatch, [Resp(429, headers={"Retry-After": "9999"})] * 3, retries=2)
    with pytest.raises(LLMUnavailable):
        c.complete_json("s", "u")
    assert len(post.calls) == 3 and max(sleeps) <= 20.0


def test_timeout_then_success(monkeypatch):
    c, post, _ = client(monkeypatch, [requests.Timeout(), Resp(200)])
    assert c.complete_json("s", "u") == {"ok": True} and len(post.calls) == 2


@pytest.mark.parametrize("status", [400, 401, 403, 404])
def test_client_errors_are_not_retried(monkeypatch, status):
    c, post, _ = client(monkeypatch, [Resp(status)])
    with pytest.raises(LLMUnavailable):
        c.complete_json("s", "u")
    assert len(post.calls) == 1


@pytest.mark.parametrize("content", ["not json at all", "[1, 2]", ""])
def test_unusable_output_raises_unavailable(monkeypatch, content):
    c, _, _ = client(monkeypatch, [Resp(content=content)])
    with pytest.raises(LLMUnavailable):
        c.complete_json("s", "u")


def test_api_key_never_in_error(monkeypatch):
    c, _, _ = client(monkeypatch, [requests.ConnectionError("failed for sk-SECRET")] * 3)
    with pytest.raises(LLMUnavailable) as exc:
        c.complete_json("s", "u")
    assert "sk-SECRET" not in str(exc.value)


def test_daily_budget_blocks_further_calls_and_resets_next_day():
    day = {"d": date(2026, 10, 6)}
    b = CallBudget(2, 0.0, today=lambda: day["d"])
    b.acquire(); b.acquire()
    with pytest.raises(LLMUnavailable):
        b.acquire()
    day["d"] = date(2026, 10, 7)
    b.acquire()
    assert b.used == 1


def test_min_interval_spacing():
    t, sleeps = {"now": 100.0}, []
    b = CallBudget(10, 4.0, clock=lambda: t["now"], sleep=sleeps.append)
    b.acquire()
    t["now"] = 101.0
    b.acquire()
    assert sleeps == [3.0]


def test_budget_counts_retries(monkeypatch):
    c, _, _ = client(monkeypatch, [Resp(500), Resp(500), Resp(200)], retries=2, budget=CallBudget(2, 0.0))
    with pytest.raises(LLMUnavailable):
        c.complete_json("s", "u")  # third attempt blocked by the budget


def test_gemini_provider_defaults(monkeypatch):
    get_settings.cache_clear()
    for k in ("LLM_BASE_URL", "LLM_API_KEY", "LLM_PROVIDER"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("LLM_PROVIDER", "gemini")
    monkeypatch.setenv("GEMINI_API_KEY", "key-from-alias")
    s = get_settings()
    assert s.llm_configured and s.llm_base_url == GEMINI_BASE_URL and s.llm_api_key == "key-from-alias"
    c = build_llm_client(s)
    assert isinstance(c, OpenAICompatibleClient) and c.base_url == GEMINI_BASE_URL
    get_settings.cache_clear()


def test_gemini_without_key_is_not_configured():
    assert not Settings(llm_provider="gemini", llm_api_key="").llm_configured
    assert Settings(llm_provider="gemini", llm_api_key="k").llm_configured
    assert not Settings(llm_provider="typo", llm_api_key="k").llm_configured
