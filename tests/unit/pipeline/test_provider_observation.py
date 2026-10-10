"""Timing observation around provider operations."""

from __future__ import annotations

from rca_ai.pipeline.provider_observation import ObservedProvider


class RecordingProvider:
    def __init__(self, result=None, error=None):
        self.request = None
        self.result = result
        self.error = error

    def complete(self, request):
        self.request = request
        if self.error is not None:
            raise self.error
        return self.result


def test_observer_reports_provider_operation_and_returns_the_original_result():
    request = {"messages": [{"content": "private prompt"}]}
    result = object()
    events = []
    provider = RecordingProvider(result=result)

    actual = ObservedProvider(provider, lambda kind, outcome=None: events.append((kind, outcome))).complete(request)

    assert actual is result
    assert provider.request is request
    assert events == [("provider_started", None), ("provider_completed", result)]


def test_observer_reports_failure_and_propagates_the_same_error():
    error = RuntimeError("provider failed")
    events = []
    provider = RecordingProvider(error=error)

    try:
        ObservedProvider(provider, lambda kind, outcome=None: events.append((kind, outcome))).complete({})
    except RuntimeError as caught:
        assert caught is error
    else:
        raise AssertionError("provider failure should propagate")

    assert events == [("provider_started", None), ("provider_failed", error)]
