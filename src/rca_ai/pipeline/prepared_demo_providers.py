"""Provider decorators used only by the prepared-demo execution path."""

from __future__ import annotations

from collections.abc import Mapping
import json
import math
import re
import time
from typing import Any, Callable

from rca_ai.providers.groq import ProviderError, ProviderHTTPError


def is_groq_json_validate_failed(error: BaseException) -> bool:
    """Match only Groq's structured HTTP 400 error code, never message text."""

    if not isinstance(error, ProviderHTTPError) or error.status_code != 400:
        return False
    if not error.response_detail:
        return False
    try:
        detail = json.loads(error.response_detail)
    except (TypeError, ValueError, json.JSONDecodeError):
        return False
    if not isinstance(detail, Mapping):
        return False
    provider_error = detail.get("error")
    return (
        isinstance(provider_error, Mapping)
        and provider_error.get("type") == "invalid_request_error"
        and provider_error.get("code") == "json_validate_failed"
    )


class ValidatorSchemaRetryProvider:
    """Retry one identical Validator request once for Groq's schema error."""

    def __init__(self, provider: Any) -> None:
        self._provider = provider

    def complete(self, request: Mapping[str, Any]) -> Any:
        try:
            return self._provider.complete(request)
        except ProviderHTTPError as error:
            if not is_groq_json_validate_failed(error):
                raise
        # The second failure intentionally propagates without another retry.
        return self._provider.complete(request)


_DURATION_PART = re.compile(r"(?P<amount>\d+(?:\.\d+)?)(?P<unit>h|m|s)")


def _reset_seconds(value: str) -> float | None:
    """Parse Groq reset values such as ``2m52.8s`` without guessing units."""

    text = value.strip()
    parts = list(_DURATION_PART.finditer(text))
    if not parts or "".join(part.group(0) for part in parts) != text:
        return None
    multipliers = {"h": 3600.0, "m": 60.0, "s": 1.0}
    seconds = sum(float(part.group("amount")) * multipliers[part.group("unit")] for part in parts)
    return seconds if math.isfinite(seconds) and seconds >= 0 else None


def _attempt_log(outcome: Any) -> tuple[Any, ...]:
    attempts = getattr(outcome, "attempt_log", ())
    return tuple(attempts) if attempts else ()


def _pacing_delay(outcome: Any, fallback_delay_seconds: float) -> float:
    attempts = _attempt_log(outcome)
    # GroqProvider already performs its normal retry/backoff inside a call.
    if any(getattr(attempt, "http_status", None) == 429 for attempt in attempts):
        return 0.0

    headers: Mapping[str, str] = {}
    if attempts:
        candidate = getattr(attempts[-1], "rate_limit_headers", {})
        if isinstance(candidate, Mapping):
            headers = candidate
    if not headers:
        candidate = getattr(outcome, "rate_limit_headers", {})
        if isinstance(candidate, Mapping):
            headers = candidate

    retry_after = next(
        (value for key, value in headers.items() if key.lower() == "retry-after"),
        None,
    )
    if retry_after is not None:
        try:
            delay = float(retry_after)
        except (TypeError, ValueError):
            delay = math.nan
        if math.isfinite(delay) and delay >= 0:
            return delay

    reset_values = [
        parsed
        for key, value in headers.items()
        if key.lower() in {"x-ratelimit-reset-requests", "x-ratelimit-reset-tokens"}
        and (parsed := _reset_seconds(str(value))) is not None
    ]
    return max(reset_values) if reset_values else fallback_delay_seconds


class ProviderCallPacer:
    """Simple shared inter-call pacing based on the prior provider response."""

    def __init__(
        self,
        *,
        fallback_delay_seconds: float = 75.0,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        if (
            isinstance(fallback_delay_seconds, bool)
            or not isinstance(fallback_delay_seconds, (int, float))
            or not math.isfinite(fallback_delay_seconds)
            or fallback_delay_seconds < 0
        ):
            raise ValueError("fallback_delay_seconds must be a finite non-negative number")
        self._fallback_delay_seconds = float(fallback_delay_seconds)
        self._sleep = sleep
        self._delay_before_next_call: float | None = None

    def before_call(self) -> None:
        delay = self._delay_before_next_call
        self._delay_before_next_call = None
        if delay is not None and delay > 0:
            self._sleep(delay)

    def after_call(self, outcome: Any) -> None:
        self._delay_before_next_call = _pacing_delay(outcome, self._fallback_delay_seconds)


class PacingProvider:
    """Apply optional shared pacing around one provider boundary."""

    def __init__(self, provider: Any, pacer: ProviderCallPacer) -> None:
        self._provider = provider
        self._pacer = pacer

    def complete(self, request: Mapping[str, Any]) -> Any:
        self._pacer.before_call()
        try:
            result = self._provider.complete(request)
        except ProviderError as error:
            self._pacer.after_call(error)
            raise
        self._pacer.after_call(result)
        return result
