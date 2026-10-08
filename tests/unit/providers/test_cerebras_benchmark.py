"""Offline contract checks for the optional Cerebras benchmark transport."""

from __future__ import annotations

import json

import httpx
import pytest

from rca_ai.providers.cerebras_benchmark import (
    CerebrasBenchmarkProvider,
    cerebras_benchmark_body,
)
from rca_ai.providers.groq import ProviderConfigurationError, ProviderHTTPError
from rca_ai.pipeline.request_budget import BudgetGuardProvider, RequestBudgetExceeded
from rca_ai.reasoning.schemas import GENERATOR_JSON_SCHEMA, VALIDATOR_JSON_SCHEMA


def _request(schema):
    return {
        "model": "openai/gpt-oss-120b",
        "reasoning_effort": "medium",
        "temperature": 0,
        "max_completion_tokens": 4096,
        "include_reasoning": False,
        "messages": [{"role": "system", "content": "Frozen instructions"},
                     {"role": "user", "content": "Frozen evidence"}],
        "response_format": {"type": "json_schema", "json_schema": {
            "name": "frozen", "strict": True, "schema": schema,
        }},
    }


@pytest.mark.parametrize("schema", [GENERATOR_JSON_SCHEMA, VALIDATOR_JSON_SCHEMA])
def test_transport_mapping_preserves_semantic_contract(schema):
    original = _request(schema)
    body = cerebras_benchmark_body(original)
    assert original["model"] == "openai/gpt-oss-120b"
    assert body == {key: value for key, value in original.items() if key != "include_reasoning"} | {
        "model": "gpt-oss-120b"
    }
    assert body["response_format"]["json_schema"]["schema"] is schema
    assert body["response_format"]["json_schema"]["strict"] is True


@pytest.mark.parametrize("schema", [GENERATOR_JSON_SCHEMA, VALIDATOR_JSON_SCHEMA])
def test_frozen_schemas_fit_documented_cerebras_strict_subset(schema):
    allowed = {"type", "properties", "required", "additionalProperties", "items", "enum"}

    def walk(node):
        assert set(node) <= allowed
        if node.get("type") == "object":
            assert node.get("additionalProperties") is False
            assert isinstance(node.get("properties"), dict)
            assert set(node.get("required", [])) <= set(node["properties"])
            for child in node["properties"].values():
                walk(child)
        if node.get("type") == "array":
            assert isinstance(node.get("items"), dict)
            walk(node["items"])

    walk(schema)
    assert len(json.dumps(schema, separators=(",", ":"))) < 5_000


@pytest.mark.parametrize("change", [
    {"temperature": 0.5},
    {"response_format": {"type": "json_object"}},
    {"include_reasoning": True},
    {"new_semantic_field": "silently dropped"},
])
def test_incompatible_contract_fails_closed(change):
    with pytest.raises(ProviderConfigurationError):
        cerebras_benchmark_body(_request(GENERATOR_JSON_SCHEMA) | change)


def test_fake_http_transport_keeps_schema_and_returns_parsed_result():
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(200, json={
            "id": "c1", "model": "gpt-oss-120b", "choices": [{
                "message": {"content": '{"hypotheses":[]}'}, "finish_reason": "stop"
            }], "usage": {"prompt_tokens": 10, "completion_tokens": 4},
        })

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result = CerebrasBenchmarkProvider(api_key="offline-key", client=client).complete(
            _request(GENERATOR_JSON_SCHEMA)
        )
    assert len(requests) == 1
    assert str(requests[0].url) == "https://api.cerebras.ai/v1/chat/completions"
    assert json.loads(requests[0].content) == cerebras_benchmark_body(_request(GENERATOR_JSON_SCHEMA))
    assert result.content == {"hypotheses": []}
    assert result.usage["prompt_tokens"] == 10
    assert "offline-key" not in repr(result)


def test_existing_budget_guard_rejects_before_cerebras_transport():
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(200, json={"choices": []})

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        guarded = BudgetGuardProvider(
            CerebrasBenchmarkProvider(api_key="offline-key", client=client),
            max_estimated_tokens=1,
        )
        with pytest.raises(RequestBudgetExceeded):
            guarded.complete(_request(GENERATOR_JSON_SCHEMA))
    assert calls == []


def test_missing_key_and_http_failure_do_not_recover_or_expose_credential(monkeypatch):
    monkeypatch.delenv("CEREBRAS_API_KEY", raising=False)
    with pytest.raises(ProviderConfigurationError):
        CerebrasBenchmarkProvider().complete(_request(GENERATOR_JSON_SCHEMA))
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(429, json={"error": {"message": "offline-key"}},
                              headers={"retry-after": "12"})

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(ProviderHTTPError) as caught:
            CerebrasBenchmarkProvider(api_key="offline-key", client=client).complete(
                _request(GENERATOR_JSON_SCHEMA)
            )
    assert len(calls) == 1
    assert caught.value.status_code == 429
    assert "offline-key" not in str(caught.value)
    assert caught.value.attempt_log[0].retry_after_seconds == 12
