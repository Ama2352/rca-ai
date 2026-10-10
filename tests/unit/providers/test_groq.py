from __future__ import annotations

import json
from typing import Any

import httpx
import pytest

from rca_ai.providers.contracts import (
    ProviderConfigurationError,
    ProviderHTTPError,
    ProviderResponseError,
    ProviderTransportError,
)
from rca_ai.providers.groq import GroqProvider


SECRET = "test-groq-key-do-not-leak"
REQUEST = {
    "model": "openai/gpt-oss-120b",
    "reasoning_effort": "medium",
    "include_reasoning": False,
    "temperature": 0,
    "max_completion_tokens": 4096,
    "messages": [{"role": "user", "content": "unchanged semantic request"}],
    "response_format": {"type": "json_schema", "json_schema": {"strict": True}},
}


def _response(content: Any = '{"hypotheses":[]}', *, finish_reason: str = "stop", usage=None):
    return httpx.Response(200, json={
        "id": "response-1",
        "model": "openai/gpt-oss-120b",
        "choices": [{"index": 0, "message": {"role": "assistant", "content": content}, "finish_reason": finish_reason}],
        "usage": usage or {"prompt_tokens": 12, "completion_tokens": 4, "total_tokens": 16,
                           "completion_tokens_details": {"reasoning_tokens": 2}},
    }, headers={"x-ratelimit-remaining-tokens": "900", "retry-after": "0"})


def _client(handler):
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_missing_environment_key_fails_before_http(monkeypatch):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    calls = []
    client = _client(lambda request: calls.append(request) or _response())
    try:
        with pytest.raises(ProviderConfigurationError) as caught:
            GroqProvider(client=client).complete(REQUEST)
        assert caught.value.attempts == 0
        assert calls == []
    finally:
        client.close()


def test_success_posts_authorization_and_returns_parsed_content_and_audit_metadata(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", SECRET)
    captured = []

    def handler(request):
        captured.append(request)
        return _response()

    client = _client(handler)
    try:
        result = GroqProvider(client=client).complete(REQUEST)
        assert captured[0].method == "POST"
        assert str(captured[0].url) == "https://api.groq.com/openai/v1/chat/completions"
        assert captured[0].headers["authorization"] == f"Bearer {SECRET}"
        assert json.loads(captured[0].content) == REQUEST
        assert result.content == {"hypotheses": []}
        assert result.raw_content == '{"hypotheses":[]}'
        assert result.http_status == 200
        assert result.attempts == 1
        assert result.finish_reason == "stop"
        assert result.usage["prompt_tokens"] == 12
        assert result.usage["completion_tokens"] == 4
        assert result.usage["completion_tokens_details"]["reasoning_tokens"] == 2
        assert result.response_id == "response-1"
        assert result.model_returned == "openai/gpt-oss-120b"
        assert result.rate_limit_headers == {
            "x-ratelimit-remaining-tokens": "900",
            "retry-after": "0",
        }
        assert result.attempt_log[0].rate_limit_headers == result.rate_limit_headers
        assert SECRET not in repr(result)
    finally:
        client.close()


def test_http_429_retries_same_body_and_honors_numeric_retry_after(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", SECRET)
    bodies = []
    calls = 0
    delays = []

    def handler(request):
        nonlocal calls
        calls += 1
        bodies.append(request.content)
        if calls == 1:
            return httpx.Response(429, json={"error": {"message": "busy"}}, headers={"retry-after": "8"})
        return _response()

    client = _client(handler)
    try:
        result = GroqProvider(client=client, sleep=delays.append).complete(REQUEST)
        assert result.attempts == 2
        assert calls == 2
        assert bodies[0] == bodies[1]
        assert delays == [8.0]
        assert result.attempt_log[0].http_status == 429
        assert result.attempt_log[0].retry_after_seconds == 8
    finally:
        client.close()


def test_fallback_retry_delays_are_five_then_fifteen_seconds(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", SECRET)
    statuses = iter((500, 502, 200))
    delays = []
    client = _client(lambda request: _response() if (status := next(statuses)) == 200 else httpx.Response(status, json={"error": "temporary"}))
    try:
        result = GroqProvider(client=client, sleep=delays.append).complete(REQUEST)
        assert result.attempts == 3
        assert delays == [5, 15]
    finally:
        client.close()


@pytest.mark.parametrize("exception", [httpx.TimeoutException("timeout"), httpx.ConnectError("transport")])
def test_timeout_and_transport_errors_retry_identical_requests(monkeypatch, exception):
    monkeypatch.setenv("GROQ_API_KEY", SECRET)
    calls = 0
    bodies = []
    delays = []

    def handler(request):
        nonlocal calls
        calls += 1
        bodies.append(request.content)
        if calls == 1:
            raise exception
        return _response()

    client = _client(handler)
    try:
        result = GroqProvider(client=client, sleep=delays.append).complete(REQUEST)
        assert result.attempts == 2
        assert bodies[0] == bodies[1]
        assert delays == [5]
        assert result.attempt_log[0].transport_error is not None
    finally:
        client.close()


@pytest.mark.parametrize("status", [400, 401, 403, 404])
def test_non_retryable_client_errors_fail_after_one_attempt(monkeypatch, status):
    monkeypatch.setenv("GROQ_API_KEY", SECRET)
    calls = []
    delays = []
    client = _client(lambda request: calls.append(request) or httpx.Response(status, json={"error": "denied"}))
    try:
        with pytest.raises(ProviderHTTPError) as caught:
            GroqProvider(client=client, sleep=delays.append).complete(REQUEST)
        assert caught.value.status_code == status
        assert caught.value.attempts == 1
        assert len(calls) == 1
        assert delays == []
    finally:
        client.close()


def test_exhausted_transient_status_raises_provider_http_error_after_three_attempts(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", SECRET)
    calls = []
    delays = []
    client = _client(lambda request: calls.append(request) or httpx.Response(503, json={"error": "unavailable"}))
    try:
        with pytest.raises(ProviderHTTPError) as caught:
            GroqProvider(client=client, sleep=delays.append).complete(REQUEST)
        assert caught.value.status_code == 503
        assert caught.value.attempts == 3
        assert len(calls) == 3
        assert delays == [5, 15]
    finally:
        client.close()


def test_provider_http_error_redacts_credentials_from_response_detail(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", SECRET)
    client = _client(lambda request: httpx.Response(400, json={"error": SECRET}))
    try:
        with pytest.raises(ProviderHTTPError) as caught:
            GroqProvider(client=client).complete(REQUEST)
        assert SECRET not in str(caught.value)
        assert SECRET not in repr(caught.value.response_detail)
        assert "[REDACTED]" in str(caught.value)
    finally:
        client.close()


@pytest.mark.parametrize("content", [None, ""])
def test_missing_or_empty_assistant_content_is_a_response_failure(monkeypatch, content):
    monkeypatch.setenv("GROQ_API_KEY", SECRET)
    client = _client(lambda request: _response(content))
    try:
        with pytest.raises(ProviderResponseError) as caught:
            GroqProvider(client=client).complete(REQUEST)
        assert caught.value.status_code == 200
        assert caught.value.attempts == 1
    finally:
        client.close()


def test_incomplete_finish_reason_is_not_retried(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", SECRET)
    calls = []
    delays = []
    client = _client(lambda request: calls.append(request) or _response(finish_reason="length"))
    try:
        with pytest.raises(ProviderResponseError):
            GroqProvider(client=client, sleep=delays.append).complete(REQUEST)
        assert len(calls) == 1
        assert delays == []
    finally:
        client.close()


def test_malformed_json_assistant_content_is_not_retried(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", SECRET)
    calls = []
    client = _client(lambda request: calls.append(request) or _response("not-json"))
    try:
        with pytest.raises(ProviderResponseError):
            GroqProvider(client=client).complete(REQUEST)
        assert len(calls) == 1
    finally:
        client.close()


def test_all_requests_use_mock_transport_without_network(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", SECRET)
    seen = []
    client = _client(lambda request: seen.append(str(request.url)) or _response())
    try:
        GroqProvider(client=client).complete(REQUEST)
        assert seen == ["https://api.groq.com/openai/v1/chat/completions"]
    finally:
        client.close()
