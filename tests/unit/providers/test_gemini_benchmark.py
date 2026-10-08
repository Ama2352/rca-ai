from __future__ import annotations

import json

import httpx
import pytest

from rca_ai.pipeline.request_budget import BudgetGuardProvider, RequestBudgetExceeded
from rca_ai.providers.gemini_benchmark import (
    GEMINI_MODEL,
    GeminiBenchmarkProvider,
    gemini_benchmark_body,
)
from rca_ai.providers.groq import ProviderConfigurationError, ProviderHTTPError, ProviderResponseError
from rca_ai.reasoning.schemas import GENERATOR_JSON_SCHEMA, VALIDATOR_JSON_SCHEMA


def _request(schema=GENERATOR_JSON_SCHEMA):
    return {
        "model": "openai/gpt-oss-120b",
        "reasoning_effort": "medium",
        "temperature": 0,
        "max_completion_tokens": 4096,
        "include_reasoning": False,
        "messages": [
            {"role": "system", "content": "Frozen instructions"},
            {"role": "user", "content": "Frozen evidence"},
        ],
        "response_format": {"type": "json_schema", "json_schema": {
            "name": "frozen", "strict": True, "schema": schema,
        }},
    }


@pytest.mark.parametrize("schema", [GENERATOR_JSON_SCHEMA, VALIDATOR_JSON_SCHEMA])
def test_gemini_body_preserves_prompt_schema_and_supported_reasoning(schema):
    original = _request(schema)
    body = gemini_benchmark_body(original)

    assert body["systemInstruction"] == {"parts": [{"text": "Frozen instructions"}]}
    assert body["contents"] == [{"role": "user", "parts": [{"text": "Frozen evidence"}]}]
    assert body["generationConfig"] == {
        "responseMimeType": "application/json",
        "responseSchema": schema,
        "maxOutputTokens": 4096,
        "thinkingConfig": {"thinkingLevel": "MEDIUM"},
    }
    assert body["generationConfig"]["responseSchema"] is schema
    assert original["messages"][1]["content"] == "Frozen evidence"
    assert GEMINI_MODEL == "gemini-3.5-flash-lite"


@pytest.mark.parametrize("change", [
    {"temperature": 0.5},
    {"reasoning_effort": "high"},
    {"include_reasoning": True},
    {"response_format": {"type": "json_object"}},
    {"messages": [{"role": "system", "content": "changed"}]},
])
def test_incompatible_request_contract_fails_closed(change):
    with pytest.raises(ProviderConfigurationError):
        gemini_benchmark_body(_request() | change)


def test_fake_transport_sends_native_strict_schema_request_and_maps_usage():
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(200, json={
            "modelVersion": GEMINI_MODEL,
            "candidates": [{
                "content": {"parts": [{"text": '{"hypotheses":[]}'}]},
                "finishReason": "STOP",
            }],
            "usageMetadata": {
                "promptTokenCount": 12,
                "candidatesTokenCount": 3,
                "totalTokenCount": 15,
            },
        })

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result = GeminiBenchmarkProvider(api_key="offline-key", client=client).complete(_request())

    assert len(requests) == 1
    assert str(requests[0].url) == (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        "gemini-3.5-flash-lite:generateContent"
    )
    assert requests[0].headers["x-goog-api-key"] == "offline-key"
    sent = json.loads(requests[0].content)
    assert sent == gemini_benchmark_body(_request())
    assert result.content == {"hypotheses": []}
    assert result.usage["promptTokenCount"] == 12
    assert result.usage["totalTokenCount"] == 15
    assert result.model_returned == GEMINI_MODEL
    assert result.attempts == 1
    assert "offline-key" not in repr(result)


def test_validator_schema_is_forwarded_without_weakening():
    request = _request(VALIDATOR_JSON_SCHEMA)
    body = gemini_benchmark_body(request)
    assert body["generationConfig"]["responseSchema"] == VALIDATOR_JSON_SCHEMA
    assert body["generationConfig"]["responseSchema"]["properties"]["decision"]["enum"] == [
        "KEEP", "KEEP_QUALIFIED", "REJECT"
    ]


@pytest.mark.parametrize("schema", [GENERATOR_JSON_SCHEMA, VALIDATOR_JSON_SCHEMA])
def test_frozen_schemas_use_only_gemini_documented_json_schema_features(schema):
    allowed = {"type", "properties", "required", "additionalProperties", "items", "enum"}

    def walk(node):
        assert set(node) <= allowed
        if node.get("type") == "object":
            assert node.get("additionalProperties") is False
            assert set(node["required"]) == set(node["properties"])
            for child in node["properties"].values():
                walk(child)
        elif node.get("type") == "array":
            walk(node["items"])
        elif node.get("type") == "string":
            assert set(node) <= {"type", "enum"}

    walk(schema)


def test_budget_guard_rejects_before_gemini_transport():
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(200, json={})

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        guarded = BudgetGuardProvider(
            GeminiBenchmarkProvider(api_key="offline-key", client=client),
            max_estimated_tokens=1,
        )
        with pytest.raises(RequestBudgetExceeded):
            guarded.complete(_request())
    assert calls == []


def test_missing_key_and_http_error_propagate_without_retry_or_secret_leak(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    with pytest.raises(ProviderConfigurationError):
        GeminiBenchmarkProvider().complete(_request())

    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(429, json={"error": {"message": "offline-key"}},
                              headers={"Retry-After": "8"})

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(ProviderHTTPError) as caught:
            GeminiBenchmarkProvider(api_key="offline-key", client=client).complete(_request())
    assert len(calls) == 1
    assert caught.value.status_code == 429
    assert "offline-key" not in str(caught.value)
    assert caught.value.attempt_log[0].retry_after_seconds == 8


def test_incomplete_or_non_json_response_is_not_accepted():
    def handler(_request):
        return httpx.Response(200, json={
            "candidates": [{"content": {"parts": [{"text": "not json"}]}, "finishReason": "STOP"}]
        })

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(ProviderResponseError):
            GeminiBenchmarkProvider(api_key="offline-key", client=client).complete(_request())
