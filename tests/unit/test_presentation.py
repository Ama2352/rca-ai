"""Semantic demo presentation keeps immutable Facts authoritative."""

from copy import deepcopy

from rca_ai.domain.models import Fact, FactEntity
from rca_ai.api.presentation import present_fact


def fact(signal: str, value: dict, field: str | None = None) -> Fact:
    return Fact(
        fact_id="F1", entity=FactEntity("resource", "checkout-pod"),
        field=field or f"{signal}.structural.series", value=value,
        source_ref="source-1", source_path="/metric/0",
    )


def test_histogram_count_rate_has_observation_unit_and_human_readable_rpc_title():
    original = fact("metric", {
        "service": "checkout", "metric": "rpc_server_call_duration_seconds_count",
        "metric_kind": "histogram_count", "unit": "reported_unit/second",
        "baseline_median": None, "incident_median": None,
        "baseline_value": 0.0, "incident_value": 0.047619,
        "change": "increased",
    })
    before = deepcopy(original.value)
    shown = present_fact(original)
    assert (shown.signal_type, shown.statistic_kind, shown.baseline, shown.incident) == (
        "metric", "histogram_observation_rate", 0.0, 0.047619,
    )
    assert shown.unit == "observations/s"
    assert shown.title == "Checkout · RPC server requests"
    assert shown.technical["metric"] == "rpc_server_call_duration_seconds_count"
    assert shown.raw.value == before
    assert original.value == before


def test_dimensionless_canonical_unit_remains_explicit_in_presentation():
    shown = present_fact(fact("metric", {
        "service": "checkout", "metric": "utilization_ratio",
        "metric_kind": "gauge", "unit": "1",
        "baseline_value": 0.2, "incident_value": 0.4,
    }))
    assert shown.unit == "1"
    assert (shown.baseline, shown.incident) == (0.2, 0.4)


def test_raw_canonical_metric_value_preserves_null_fields_and_values():
    value = {
        "metric": "rpc_server_call_duration_seconds_count",
        "metric_kind": "histogram_count", "unit": "reported_unit/second",
        "baseline_value": 0.0, "incident_value": 0.047619,
        "start": None, "end": None, "duration_ms": None,
        "trace_id": None, "span_id": None,
    }
    original = fact("metric", value)
    before = deepcopy(original.value)

    shown = present_fact(original)

    assert shown.raw == original
    assert shown.raw.value == before


def test_appeared_metric_does_not_construct_null_comparison():
    shown = present_fact(fact("metric", {
        "service": "checkout", "metric": "duration_mean", "unit": "seconds",
        "metric_kind": "histogram_mean", "change": "appeared",
        "baseline_value": None, "incident_value": 0.285,
    }))
    assert shown.change == "appeared"
    assert shown.baseline is None
    assert shown.incident == 0.285
    assert shown.unit == "seconds"


def test_trace_prefers_paired_median_and_does_not_infer_edge_from_rpc_name():
    shown = present_fact(fact("trace", {
        "kind": "operation", "service": "checkout",
        "operation_or_callee": "oteldemo.PaymentService/Charge",
        "baseline_median_ms": 1.986, "incident_median_ms": 6.368,
        "baseline_mean_ms": 5.1148, "incident_mean_ms": 17.7137,
    }, "trace.structural.operation"))
    assert (shown.statistic_kind, shown.baseline, shown.incident, shown.unit) == (
        "median_latency", 1.986, 6.368, "ms",
    )
    assert shown.source_service == "checkout"
    assert shown.destination_service is None
    assert "PaymentService" not in shown.title


def test_explicit_trace_edge_has_destination_and_mean_fallback():
    shown = present_fact(fact("trace", {
        "kind": "edge", "service": "checkout", "operation_or_callee": "payment",
        "baseline_median_ms": None, "incident_median_ms": None,
        "baseline_mean_ms": 2.1792, "incident_mean_ms": 14.3305,
    }, "trace.structural.edge"))
    assert (shown.destination_service, shown.statistic_kind, shown.unit) == (
        "payment", "average_latency", "ms",
    )


def test_log_count_and_kubernetes_state_are_source_faithful():
    log = present_fact(fact("log", {
        "service": "payment", "severity": "WARN",
        "pattern": "Payment request failed. Invalid token.",
        "baseline_count": 0, "incident_count": 6, "change": "increased",
    }, "log.structural.pattern"))
    assert (log.statistic_kind, log.unit, log.baseline, log.incident) == (
        "occurrences", "occurrences", 0, 6,
    )
    assert log.preview == "Payment request failed. Invalid token."
    assert log.title.startswith("Payment WARN log")
    state = present_fact(fact("kubernetes", {
        "deployment": "payment", "phase": "Running", "ready": True,
    }, "kubernetes.structural.state"))
    assert state.state == "Running"
    assert state.baseline is None and state.incident is None
    assert "Running" in state.title


def test_unknown_unit_and_nonfinite_values_remain_unavailable():
    shown = present_fact(fact("metric", {
        "metric": "mystery", "baseline_value": float("nan"),
        "incident_value": float("inf"), "unit": "reported_unit",
    }))
    assert shown.unit is None
    assert shown.baseline is None and shown.incident is None
    assert shown.statistic_kind == "value"
