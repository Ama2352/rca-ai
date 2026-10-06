import pytest

from rca_ai.pipeline.request_budget import (
    BudgetGuardProvider,
    RequestBudgetExceeded,
    request_size,
)


class RecordingProvider:
    def __init__(self):
        self.requests = []

    def complete(self, request):
        self.requests.append(request)
        return {"ok": True}


def test_guard_accepts_request_at_estimated_token_limit_unchanged():
    provider = RecordingProvider()
    request = {"a": ""}  # Compact JSON is exactly 8 bytes, or 2 estimated tokens.

    guarded = BudgetGuardProvider(provider, max_estimated_tokens=2)

    assert request_size(request) == (8, 2)
    assert guarded.complete(request) == {"ok": True}
    assert provider.requests == [request]
    assert provider.requests[0] is request


def test_guard_rejects_oversize_before_provider_and_reports_estimate():
    provider = RecordingProvider()
    request = {"a": "x"}  # Compact JSON is 9 bytes, or 3 estimated tokens.

    guarded = BudgetGuardProvider(provider, max_estimated_tokens=2)

    with pytest.raises(RequestBudgetExceeded) as raised:
        guarded.complete(request)

    assert raised.value.request_bytes == 9
    assert raised.value.estimated_tokens == 3
    assert raised.value.max_estimated_tokens == 2
    assert provider.requests == []


def test_guard_rejects_invalid_budget_configuration():
    with pytest.raises(ValueError, match="positive integer"):
        BudgetGuardProvider(RecordingProvider(), max_estimated_tokens=0)
