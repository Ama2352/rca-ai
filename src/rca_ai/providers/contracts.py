"""Shared transport results and errors for provider adapters."""

from __future__ import annotations

from dataclasses import dataclass, field
from collections.abc import Mapping
from typing import Any


@dataclass(frozen=True)
class ProviderAttempt:
    """Operational facts about one HTTP attempt, excluding request credentials."""

    number: int
    http_status: int | None = None
    latency_seconds: float = 0.0
    retry_after_seconds: float | None = None
    rate_limit_headers: Mapping[str, str] = field(default_factory=dict)
    transport_error: str | None = None


@dataclass(frozen=True)
class ProviderResult:
    """Parsed generic JSON content plus provider metadata used for auditing."""

    content: Any
    raw_content: str
    http_status: int
    attempts: int
    response_id: str | None
    model_returned: str | None
    finish_reason: str
    usage: Mapping[str, Any]
    latency_seconds: float
    rate_limit_headers: Mapping[str, str]
    attempt_log: tuple[ProviderAttempt, ...]


class ProviderError(RuntimeError):
    """Base execution failure; semantic layers must not treat it as RCA output."""

    def __init__(
        self,
        message: str,
        *,
        attempts: int,
        status_code: int | None = None,
        response_detail: str | None = None,
        attempt_log: tuple[ProviderAttempt, ...] = (),
    ) -> None:
        super().__init__(message)
        self.attempts = attempts
        self.status_code = status_code
        self.response_detail = response_detail
        self.attempt_log = attempt_log


class ProviderConfigurationError(ProviderError):
    """Local configuration failure detected before a network attempt."""


class ProviderHTTPError(ProviderError):
    """Non-success HTTP response or exhausted retryable HTTP response."""


class ProviderTransportError(ProviderError):
    """Exhausted timeout/transport attempts without an HTTP response."""


class ProviderResponseError(ProviderError):
    """HTTP succeeded but did not contain a completed JSON assistant response."""
