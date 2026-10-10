"""Groq Chat Completions transport with the frozen identical-request retry.

This boundary owns credentials, HTTP details, bounded retries, and generic
JSON-content parsing so reasoning modules can treat provider errors as
execution failures rather than semantic abstentions.
"""

from __future__ import annotations

import json
import math
import os
import time
from collections.abc import Callable, Mapping
from typing import Any

import httpx

from rca_ai.providers.contracts import (
    ProviderAttempt,
    ProviderConfigurationError,
    ProviderError,
    ProviderHTTPError,
    ProviderResponseError,
    ProviderResult,
    ProviderTransportError,
)


GROQ_CHAT_COMPLETIONS_URL = "https://api.groq.com/openai/v1/chat/completions"
_MAX_ATTEMPTS = 3


class GroqProvider:
    """Send an already-built JSON request to Groq and parse completed JSON content.

    The provider never constructs semantic prompts or schemas. Credentials are
    resolved here from `GROQ_API_KEY` because they are transport configuration,
    not domain or reasoning data. One serialized body is reused on every retry
    to prevent a transient failure from changing the semantic request.
    """

    def __init__(
        self,
        *,
        api_key: str | None = None,
        client: httpx.Client | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._api_key = api_key
        self._client = client
        self._sleep = sleep

    def _credential(self) -> str:
        credential = self._api_key if self._api_key is not None else os.getenv("GROQ_API_KEY")
        if not credential or not credential.strip():
            raise ProviderConfigurationError(
                "GROQ_API_KEY is required for a Groq request", attempts=0
            )
        return credential.strip()

    @staticmethod
    def _rate_limit_headers(response: httpx.Response) -> dict[str, str]:
        return {
            key: value for key, value in response.headers.items()
            if key.lower().startswith("x-ratelimit") or key.lower() == "retry-after"
        }

    @staticmethod
    def _retry_after(response: httpx.Response) -> float | None:
        try:
            value = float(response.headers.get("retry-after", ""))
        except (TypeError, ValueError):
            return None
        return value if math.isfinite(value) and value >= 0 else None

    @staticmethod
    def _safe_response_detail(response: httpx.Response, credential: str) -> str:
        try:
            payload: Any = response.json()
            detail = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        except (ValueError, json.JSONDecodeError):
            detail = response.text
        return detail.replace(credential, "[REDACTED]")

    def _post(self, body: bytes, credential: str) -> httpx.Response:
        headers = {
            "Authorization": f"Bearer {credential}",
            "Content-Type": "application/json",
        }
        if self._client is not None:
            return self._client.post(GROQ_CHAT_COMPLETIONS_URL, content=body, headers=headers)
        timeout = httpx.Timeout(90.0, connect=15.0)
        with httpx.Client(timeout=timeout) as client:
            return client.post(GROQ_CHAT_COMPLETIONS_URL, content=body, headers=headers)

    def complete(self, request: Mapping[str, Any]) -> ProviderResult:
        """Complete one frozen request; transient failures retry identically at most twice."""

        credential = self._credential()
        try:
            body = json.dumps(request, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        except (TypeError, ValueError) as exc:
            raise ProviderConfigurationError(
                "Groq request must be JSON serializable", attempts=0
            ) from None

        attempt_log: list[ProviderAttempt] = []
        retryable_statuses = {429, 500, 502, 503, 504}
        for number in range(1, _MAX_ATTEMPTS + 1):
            if number > 1:
                previous = attempt_log[-1]
                fallback = 5 if number == 2 else 15
                delay = max(fallback, previous.retry_after_seconds or 0)
                self._sleep(delay)

            started = time.monotonic()
            try:
                response = self._post(body, credential)
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                attempt_log.append(ProviderAttempt(
                    number=number,
                    latency_seconds=time.monotonic() - started,
                    transport_error=type(exc).__name__,
                ))
                if number < _MAX_ATTEMPTS:
                    continue
                raise ProviderTransportError(
                    f"Groq transport failed after {number} attempts ({type(exc).__name__})",
                    attempts=number,
                    attempt_log=tuple(attempt_log),
                ) from None

            latency = time.monotonic() - started
            headers = self._rate_limit_headers(response)
            retry_after = self._retry_after(response) if response.status_code == 429 else None
            attempt_log.append(ProviderAttempt(
                number=number,
                http_status=response.status_code,
                latency_seconds=latency,
                retry_after_seconds=retry_after,
                rate_limit_headers=headers,
            ))

            if response.status_code != 200:
                detail = self._safe_response_detail(response, credential)
                if response.status_code in retryable_statuses and number < _MAX_ATTEMPTS:
                    continue
                raise ProviderHTTPError(
                    f"Groq returned HTTP {response.status_code} after {number} attempt(s): {detail}",
                    attempts=number,
                    status_code=response.status_code,
                    response_detail=detail,
                    attempt_log=tuple(attempt_log),
                )

            try:
                payload = response.json()
            except (ValueError, json.JSONDecodeError):
                raise ProviderResponseError(
                    "Groq returned HTTP 200 with a non-JSON response",
                    attempts=number,
                    status_code=200,
                    attempt_log=tuple(attempt_log),
                ) from None
            if not isinstance(payload, Mapping):
                raise ProviderResponseError(
                    "Groq response must be a JSON object", attempts=number,
                    status_code=200, attempt_log=tuple(attempt_log),
                )
            choices = payload.get("choices")
            choice = choices[0] if isinstance(choices, list) and choices else None
            message = choice.get("message") if isinstance(choice, Mapping) else None
            content = message.get("content") if isinstance(message, Mapping) else None
            finish_reason = choice.get("finish_reason") if isinstance(choice, Mapping) else None
            if not isinstance(content, str) or not content:
                raise ProviderResponseError(
                    "Groq response is missing non-empty assistant content", attempts=number,
                    status_code=200, attempt_log=tuple(attempt_log),
                )
            if finish_reason != "stop":
                raise ProviderResponseError(
                    f"Groq structured completion was incomplete (finish_reason={finish_reason!r})",
                    attempts=number,
                    status_code=200,
                    attempt_log=tuple(attempt_log),
                )
            try:
                parsed_content = json.loads(content)
            except (ValueError, json.JSONDecodeError):
                raise ProviderResponseError(
                    "Groq assistant content is not valid JSON", attempts=number,
                    status_code=200, attempt_log=tuple(attempt_log),
                ) from None

            usage = payload.get("usage", {})
            if not isinstance(usage, Mapping):
                usage = {}
            return ProviderResult(
                content=parsed_content,
                raw_content=content,
                http_status=200,
                attempts=number,
                response_id=payload.get("id"),
                model_returned=payload.get("model"),
                finish_reason=finish_reason,
                usage=usage,
                latency_seconds=latency,
                rate_limit_headers=headers,
                attempt_log=tuple(attempt_log),
            )

        raise ProviderError("Groq provider attempts exhausted", attempts=len(attempt_log), attempt_log=tuple(attempt_log))
