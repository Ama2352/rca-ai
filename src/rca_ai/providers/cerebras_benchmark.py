"""Cerebras transport used by the prepared-demo Validator and benchmark.

It accepts
the frozen Groq-shaped reasoning request, changing only the provider model ID
and omitting Groq's transport-only ``include_reasoning`` switch. All prompts,
schema, evidence, and reasoning settings stay identical.
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


CEREBRAS_CHAT_COMPLETIONS_URL = "https://api.cerebras.ai/v1/chat/completions"
CEREBRAS_MODEL = "gpt-oss-120b"
_FIELDS = frozenset({
    "model", "messages", "response_format", "reasoning_effort", "temperature",
    "max_completion_tokens", "include_reasoning",
})


def cerebras_benchmark_body(request: Mapping[str, Any]) -> dict[str, Any]:
    """Map only documented transport-envelope differences; reject semantic drift."""

    response_format = request.get("response_format")
    json_schema = response_format.get("json_schema") if isinstance(response_format, Mapping) else None
    schema = json_schema.get("schema") if isinstance(json_schema, Mapping) else None
    if (
        frozenset(request) != _FIELDS
        or request.get("model") != "openai/gpt-oss-120b"
        or request.get("reasoning_effort") != GENERATOR_REASONING_EFFORT
        or request.get("temperature") != GENERATOR_TEMPERATURE
        or request.get("max_completion_tokens") != GENERATOR_MAX_COMPLETION_TOKENS
        or request.get("include_reasoning") is not GENERATOR_INCLUDE_REASONING
        or not isinstance(request.get("messages"), list)
        or not isinstance(response_format, Mapping)
        or response_format.get("type") != "json_schema"
        or not isinstance(json_schema, Mapping)
        or json_schema.get("strict") is not True
        or schema not in (GENERATOR_JSON_SCHEMA, VALIDATOR_JSON_SCHEMA)
    ):
        raise ProviderConfigurationError(
            "Cerebras transport requires the unchanged frozen semantic request",
            attempts=0,
        )
    return {key: value for key, value in request.items() if key != "include_reasoning"} | {
        "model": CEREBRAS_MODEL,
    }


class CerebrasBenchmarkProvider:
    """One-attempt prepared-demo transport; no fallback, repair, or provider switch."""

    def __init__(self, *, api_key: str | None = None, client: httpx.Client | None = None) -> None:
        self._api_key = api_key
        self._client = client

    def complete(self, request: Mapping[str, Any]) -> ProviderResult:
        body = cerebras_benchmark_body(request)
        credential = self._api_key if self._api_key is not None else os.getenv("CEREBRAS_API_KEY")
        if not credential or not credential.strip():
            raise ProviderConfigurationError("CEREBRAS_API_KEY is required", attempts=0)
        credential = credential.strip()
        payload = json.dumps(body, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        headers = {"Authorization": f"Bearer {credential}", "Content-Type": "application/json"}
        started = time.monotonic()
        try:
            if self._client is None:
                with httpx.Client(timeout=httpx.Timeout(90.0, connect=15.0)) as client:
                    response = client.post(CEREBRAS_CHAT_COMPLETIONS_URL, content=payload, headers=headers)
            else:
                response = self._client.post(CEREBRAS_CHAT_COMPLETIONS_URL, content=payload, headers=headers)
        except (httpx.TimeoutException, httpx.TransportError) as exc:
            latency = time.monotonic() - started
            attempt = ProviderAttempt(1, latency_seconds=latency, transport_error=type(exc).__name__)
            raise ProviderTransportError(
                f"Cerebras transport failed ({type(exc).__name__})", attempts=1,
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
        attempt = ProviderAttempt(1, response.status_code, latency,
                                  retry_after_seconds=retry_after,
                                  rate_limit_headers=rate_headers)
        if response.status_code != 200:
            try:
                detail = json.dumps(response.json(), ensure_ascii=False, separators=(",", ":"))
            except ValueError:
                detail = response.text
            detail = detail.replace(credential, "[REDACTED]")
            raise ProviderHTTPError(
                f"Cerebras returned HTTP {response.status_code}: {detail}", attempts=1,
                status_code=response.status_code, response_detail=detail, attempt_log=(attempt,),
            )
        try:
            result = response.json()
            choice = result["choices"][0]
            raw_content = choice["message"]["content"]
            finish_reason = choice["finish_reason"]
            parsed = json.loads(raw_content)
            if not raw_content or finish_reason != "stop":
                raise ValueError("incomplete content")
        except (ValueError, TypeError, KeyError, IndexError):
            raise ProviderResponseError(
                "Cerebras returned an incomplete or non-JSON structured completion",
                attempts=1, status_code=200, attempt_log=(attempt,),
            ) from None
        usage = result.get("usage", {})
        return ProviderResult(
            content=parsed, raw_content=raw_content, http_status=200, attempts=1,
            response_id=result.get("id"), model_returned=result.get("model"),
            finish_reason=finish_reason, usage=usage if isinstance(usage, Mapping) else {},
            latency_seconds=latency, rate_limit_headers=rate_headers, attempt_log=(attempt,),
        )
