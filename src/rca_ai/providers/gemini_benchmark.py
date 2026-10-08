"""Isolated Gemini transport for controlled prepared-demo benchmarks.

The adapter accepts only the frozen Groq semantic request and maps its prompt,
JSON schema, output limit, and reasoning effort to Google's GenerateContent
envelope. Gemini 3.5 recommends leaving temperature at its default, so the
frozen temperature field is intentionally not forwarded. This adapter is not
used by the default provider factory and performs one HTTP attempt only.
"""

from __future__ import annotations

import json
import math
import os
import time
from collections.abc import Mapping
from typing import Any

import httpx

from rca_ai.providers.groq import (
    ProviderAttempt,
    ProviderConfigurationError,
    ProviderHTTPError,
    ProviderResponseError,
    ProviderResult,
    ProviderTransportError,
)
from rca_ai.reasoning.generator import (
    GENERATOR_INCLUDE_REASONING,
    GENERATOR_MAX_COMPLETION_TOKENS,
    GENERATOR_REASONING_EFFORT,
    GENERATOR_TEMPERATURE,
)
from rca_ai.reasoning.schemas import GENERATOR_JSON_SCHEMA, VALIDATOR_JSON_SCHEMA


GEMINI_MODEL = "gemini-3.5-flash-lite"
GEMINI_GENERATE_CONTENT_URL = (
    "https://generativelanguage.googleapis.com/v1beta/models/"
    f"{GEMINI_MODEL}:generateContent"
)
_FIELDS = frozenset({
    "model", "messages", "response_format", "reasoning_effort", "temperature",
    "max_completion_tokens", "include_reasoning",
})


def _assert_gemini_schema_subset(schema: Any) -> None:
    """Reject unsupported JSON Schema constructs instead of silently dropping them."""

    allowed = {"type", "properties", "required", "additionalProperties", "items", "enum"}
    if not isinstance(schema, Mapping) or set(schema) - allowed:
        raise ProviderConfigurationError(
            "Frozen schema contains constructs not supported by the Gemini benchmark adapter",
            attempts=0,
        )
    kind = schema.get("type")
    if kind == "object":
        properties = schema.get("properties")
        required = schema.get("required")
        if (
            schema.get("additionalProperties") is not False
            or not isinstance(properties, Mapping)
            or not isinstance(required, list)
            or not set(required) <= set(properties)
        ):
            raise ProviderConfigurationError("Frozen object schema is not safely mappable", attempts=0)
        for child in properties.values():
            _assert_gemini_schema_subset(child)
    elif kind == "array":
        if "items" not in schema:
            raise ProviderConfigurationError("Frozen array schema requires item schema", attempts=0)
        _assert_gemini_schema_subset(schema["items"])
    elif kind == "string":
        if set(schema) - {"type", "enum"}:
            raise ProviderConfigurationError("Frozen string schema is not safely mappable", attempts=0)
    else:
        raise ProviderConfigurationError(f"Unsupported Gemini schema type: {kind!r}", attempts=0)


def gemini_benchmark_body(request: Mapping[str, Any]) -> dict[str, Any]:
    """Map the exact frozen request into Google's strict structured-output API."""

    response_format = request.get("response_format")
    json_schema = response_format.get("json_schema") if isinstance(response_format, Mapping) else None
    schema = json_schema.get("schema") if isinstance(json_schema, Mapping) else None
    messages = request.get("messages")
    if (
        frozenset(request) != _FIELDS
        or request.get("model") != "openai/gpt-oss-120b"
        or request.get("reasoning_effort") != GENERATOR_REASONING_EFFORT
        or request.get("temperature") != GENERATOR_TEMPERATURE
        or request.get("max_completion_tokens") != GENERATOR_MAX_COMPLETION_TOKENS
        or request.get("include_reasoning") is not GENERATOR_INCLUDE_REASONING
        or not isinstance(messages, list)
        or len(messages) != 2
        or not all(isinstance(message, Mapping) for message in messages)
        or messages[0].get("role") != "system"
        or messages[1].get("role") != "user"
        or not all(isinstance(message.get("content"), str) for message in messages)
        or not isinstance(response_format, Mapping)
        or response_format.get("type") != "json_schema"
        or not isinstance(json_schema, Mapping)
        or json_schema.get("strict") is not True
        or schema not in (GENERATOR_JSON_SCHEMA, VALIDATOR_JSON_SCHEMA)
    ):
        raise ProviderConfigurationError(
            "Gemini benchmark requires an unchanged frozen Generator or Validator request",
            attempts=0,
        )
    _assert_gemini_schema_subset(schema)

    return {
        "systemInstruction": {"parts": [{"text": messages[0]["content"]}]},
        "contents": [{"role": "user", "parts": [{"text": messages[1]["content"]}]}],
        "generationConfig": {
            "responseMimeType": "application/json",
            "responseSchema": schema,
            "maxOutputTokens": GENERATOR_MAX_COMPLETION_TOKENS,
            "thinkingConfig": {"thinkingLevel": "MEDIUM"},
        },
    }


class GeminiBenchmarkProvider:
    """Single-attempt benchmark transport; no fallback, repair, or provider switch."""

    def __init__(self, *, api_key: str | None = None, client: httpx.Client | None = None) -> None:
        self._api_key = api_key
        self._client = client

    def complete(self, request: Mapping[str, Any]) -> ProviderResult:
        body = gemini_benchmark_body(request)
        credential = self._api_key if self._api_key is not None else os.getenv("GEMINI_API_KEY")
        if not credential or not credential.strip():
            raise ProviderConfigurationError("GEMINI_API_KEY is required", attempts=0)
        credential = credential.strip()
        payload = json.dumps(body, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        headers = {"x-goog-api-key": credential, "Content-Type": "application/json"}
        started = time.monotonic()
        try:
            if self._client is None:
                with httpx.Client(timeout=httpx.Timeout(90.0, connect=15.0)) as client:
                    response = client.post(GEMINI_GENERATE_CONTENT_URL, content=payload, headers=headers)
            else:
                response = self._client.post(GEMINI_GENERATE_CONTENT_URL, content=payload, headers=headers)
        except (httpx.TimeoutException, httpx.TransportError) as exc:
            latency = time.monotonic() - started
            attempt = ProviderAttempt(1, latency_seconds=latency, transport_error=type(exc).__name__)
            raise ProviderTransportError(
                f"Gemini transport failed ({type(exc).__name__})", attempts=1,
                attempt_log=(attempt,),
            ) from None

        latency = time.monotonic() - started
        rate_headers = {
            key: value for key, value in response.headers.items()
            if key.lower().startswith("x-ratelimit") or key.lower() == "retry-after"
        }
        try:
            retry_after = float(response.headers.get("retry-after", ""))
        except (TypeError, ValueError):
            retry_after = None
        if retry_after is not None and (not math.isfinite(retry_after) or retry_after < 0):
            retry_after = None
        attempt = ProviderAttempt(
            1, response.status_code, latency, retry_after_seconds=retry_after,
            rate_limit_headers=rate_headers,
        )
        if response.status_code != 200:
            try:
                detail = json.dumps(response.json(), ensure_ascii=False, separators=(",", ":"))
            except ValueError:
                detail = response.text
            detail = detail.replace(credential, "[REDACTED]")
            raise ProviderHTTPError(
                f"Gemini returned HTTP {response.status_code}: {detail}", attempts=1,
                status_code=response.status_code, response_detail=detail, attempt_log=(attempt,),
            )

        try:
            result = response.json()
            candidate = result["candidates"][0]
            finish_reason = candidate["finishReason"]
            parts = candidate["content"]["parts"]
            text_parts = [part["text"] for part in parts if isinstance(part.get("text"), str)
                          and not part.get("thought", False)]
            raw_content = "".join(text_parts)
            if not raw_content or finish_reason != "STOP":
                raise ValueError("incomplete content")
            parsed = json.loads(raw_content)
            if not isinstance(parsed, Mapping):
                raise ValueError("structured output is not an object")
        except (ValueError, TypeError, KeyError, IndexError):
            raise ProviderResponseError(
                "Gemini returned an incomplete or non-object JSON structured completion",
                attempts=1, status_code=200, attempt_log=(attempt,),
            ) from None

        usage = result.get("usageMetadata", {})
        return ProviderResult(
            content=parsed, raw_content=raw_content, http_status=200, attempts=1,
            response_id=result.get("responseId"), model_returned=result.get("modelVersion", GEMINI_MODEL),
            finish_reason="stop", usage=usage if isinstance(usage, Mapping) else {},
            latency_seconds=latency, rate_limit_headers=rate_headers, attempt_log=(attempt,),
        )
