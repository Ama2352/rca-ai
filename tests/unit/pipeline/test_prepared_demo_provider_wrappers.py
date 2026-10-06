"""Provider-boundary retry and pacing contracts for the prepared demo."""

from __future__ import annotations

import json

import pytest

from rca_ai.pipeline.prepared_demo_providers import (
    ProviderCallPacer,
    PacingProvider,
    ValidatorSchemaRetryProvider,
)
from rca_ai.pipeline.request_budget import BudgetGuardProvider
from rca_ai.providers.groq import ProviderAttempt, ProviderError, ProviderHTTPError, ProviderResult


def _json_validate_error(*, status_code=400, error_type="invalid_request_error", code="json_validate_failed", headers=None):
    detail = json.dumps({"error": {"type": error_type, "code": code, "message": "diagnostic"}})
    attempts = ()
    if headers is not None:
        attempts = (ProviderAttempt(number=1, http_status=status_code, rate_limit_headers=headers),)
    return ProviderHTTPError(
        "provider error",
        attempts=1,
        status_code=status_code,
        response_detail=detail,
        attempt_log=attempts,
    )


def _result(*, headers=None, attempts=()):
    return ProviderResult(
        content={"ok": True},
        raw_content='{"ok":true}',
        http_status=200,
        attempts=max(1, len(attempts)),
        response_id="offline",
        model_returned="offline",
        finish_reason="stop",
        usage={},
        latency_seconds=0.0,
        rate_limit_headers=headers or {},
        attempt_log=attempts,
    )


class SequenceProvider:
    def __init__(self, outcomes):
        self.outcomes = list(outcomes)
        self.requests = []

    def complete(self, request):
        self.requests.append(request)
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome


def test_validator_retry_returns_first_success_without_retry():
    request = {"messages": [{"role": "user", "content": "unchanged"}]}
    result = _result()
    provider = SequenceProvider([result])

    actual = ValidatorSchemaRetryProvider(provider).complete(request)

    assert actual is result
    assert provider.requests == [request]


def test_validator_retries_only_structured_json_validate_failed_once_with_identical_request():
    request = {"messages": [{"role": "user", "content": "unchanged"}]}
    result = _result()
    provider = SequenceProvider([_json_validate_error(), result])

    actual = ValidatorSchemaRetryProvider(provider).complete(request)

    assert actual is result
    assert len(provider.requests) == 2
    assert provider.requests[0] is request
    assert provider.requests[1] is request


def test_validator_retry_propagates_second_matching_failure_without_third_attempt():
    request = {"same": True}
    first = _json_validate_error()
    second = _json_validate_error()
    provider = SequenceProvider([first, second])

    with pytest.raises(ProviderHTTPError) as raised:
        ValidatorSchemaRetryProvider(provider).complete(request)

    assert raised.value is second
    assert len(provider.requests) == 2
    assert all(item is request for item in provider.requests)


@pytest.mark.parametrize(
    "error",
    [
        _json_validate_error(status_code=400, code="invalid_request"),
        _json_validate_error(status_code=400, error_type="authentication_error"),
        _json_validate_error(status_code=401),
        _json_validate_error(status_code=403),
        _json_validate_error(status_code=429),
        ProviderError("unrelated provider failure", attempts=1),
    ],
)
def test_validator_does_not_retry_unrelated_provider_errors(error):
    provider = SequenceProvider([error])

    with pytest.raises(type(error)):
        ValidatorSchemaRetryProvider(provider).complete({"request": "original"})

    assert len(provider.requests) == 1


def test_validator_retry_requires_parseable_structured_error_detail():
    error = ProviderHTTPError(
        "unstructured message mentions json_validate_failed",
        attempts=1,
        status_code=400,
        response_detail="not-json",
    )
    provider = SequenceProvider([error])

    with pytest.raises(ProviderHTTPError):
        ValidatorSchemaRetryProvider(provider).complete({"request": "original"})

    assert len(provider.requests) == 1


def test_each_validator_recovery_attempt_passes_through_budget_guard():
    class CountingBudgetGuard(BudgetGuardProvider):
        def __init__(self, provider):
            super().__init__(provider, max_estimated_tokens=100)
            self.checked = []

        def complete(self, request):
            self.checked.append(request)
            return super().complete(request)

    request = {"messages": [{"role": "user", "content": "same bytes"}]}
    result = _result()
    provider = SequenceProvider([_json_validate_error(), result])
    budget_guard = CountingBudgetGuard(provider)

    actual = ValidatorSchemaRetryProvider(budget_guard).complete(request)

    assert actual is result
    assert len(budget_guard.checked) == 2
    assert all(item is request for item in budget_guard.checked)


def test_pacer_uses_configured_fallback_between_calls_when_headers_absent():
    delays = []
    provider = SequenceProvider([_result(), _result()])
    paced = PacingProvider(provider, ProviderCallPacer(fallback_delay_seconds=75, sleep=delays.append))

    paced.complete({"n": 1})
    paced.complete({"n": 2})

    assert delays == [75]


def test_pacer_honors_rate_limit_reset_headers_between_calls():
    delays = []
    provider = SequenceProvider([
        _result(headers={
            "x-ratelimit-reset-requests": "2m5s",
            "x-ratelimit-reset-tokens": "42.3s",
        }),
        _result(),
    ])
    paced = PacingProvider(provider, ProviderCallPacer(fallback_delay_seconds=75, sleep=delays.append))

    paced.complete({"n": 1})
    paced.complete({"n": 2})

    assert delays == [125]


def test_pacer_prefers_retry_after_header():
    delays = []
    provider = SequenceProvider([
        _result(headers={
            "retry-after": "12",
            "x-ratelimit-reset-requests": "2m5s",
        }),
        _result(),
    ])
    paced = PacingProvider(provider, ProviderCallPacer(fallback_delay_seconds=75, sleep=delays.append))

    paced.complete({"n": 1})
    paced.complete({"n": 2})

    assert delays == [12]


def test_pacer_does_not_duplicate_wait_after_provider_handled_429_retry():
    delays = []
    attempts = (
        ProviderAttempt(number=1, http_status=429, retry_after_seconds=20),
        ProviderAttempt(number=2, http_status=200),
    )
    provider = SequenceProvider([_result(attempts=attempts), _result()])
    paced = PacingProvider(provider, ProviderCallPacer(fallback_delay_seconds=75, sleep=delays.append))

    paced.complete({"n": 1})
    paced.complete({"n": 2})

    assert delays == []


def test_recovery_attempt_is_paced_and_remains_budget_checked():
    delays = []
    request = {"messages": [{"role": "user", "content": "same"}]}
    provider = SequenceProvider([_json_validate_error(), _result()])
    guarded = BudgetGuardProvider(provider, max_estimated_tokens=100)
    paced = PacingProvider(guarded, ProviderCallPacer(fallback_delay_seconds=75, sleep=delays.append))

    result = ValidatorSchemaRetryProvider(paced).complete(request)

    assert result.content == {"ok": True}
    assert len(provider.requests) == 2
    assert all(item is request for item in provider.requests)
    assert delays == [75]
