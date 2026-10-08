"""Source-faithful semantics for the prepared-demo UI; never alters RCA Facts."""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any, Mapping

from rca_ai.domain.models import Fact


@dataclass(frozen=True)
class EvidencePresentation:
    id: str
    signal_type: str
    title: str
    statistic_kind: str | None
    baseline: float | int | None
    incident: float | int | None
    unit: str | None
    change: str | None
    source_service: str | None
    destination_service: str | None
    operation: str | None
    severity: str | None
    state: str | None
    preview: str | None
    technical: Mapping[str, Any]
    raw: Fact


def _string(value: Any) -> str | None:
    return value if isinstance(value, str) and value.strip() else None


def _number(value: Any) -> int | float | None:
    return value if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) else None


def _pair(value: Mapping[str, Any], before: str, after: str) -> tuple[int | float | None, int | float | None]:
    first, second = _number(value.get(before)), _number(value.get(after))
    return (first, second) if first is not None and second is not None else (None, None)


def _label(value: str) -> str:
    return value.replace("_", " ").replace(".", " ").strip().title()


def _base(fact: Fact, signal: str, title: str, value: Mapping[str, Any], **overrides: Any) -> EvidencePresentation:
    fields: dict[str, Any] = {
        "id": fact.fact_id,
        "signal_type": signal,
        "title": title,
        "statistic_kind": None,
        "baseline": None,
        "incident": None,
        "unit": None,
        "change": _string(value.get("change")),
        "source_service": _string(value.get("service")),
        "destination_service": None,
        "operation": None,
        "severity": None,
        "state": None,
        "preview": None,
        "technical": {
            "field": fact.field, "entity": {"type": fact.entity.type, "id": fact.entity.id},
            "source_ref": fact.source_ref, "source_path": fact.source_path,
            "lane": value.get("lane"),
        },
        "raw": fact,
    }
    fields.update(overrides)
    return EvidencePresentation(**fields)


def present_fact(fact: Fact) -> EvidencePresentation:
    """Project a Fact to explicit display semantics without mutating or scoring it."""

    value = fact.value if isinstance(fact.value, Mapping) else {}
    signal = fact.field.split(".", 1)[0]
    service = _string(value.get("service"))
    owner = _label(service) if service else _label(fact.entity.id)
    change = _string(value.get("change"))

    if signal == "metric":
        metric = _string(value.get("metric"))
        metric_kind = _string(value.get("metric_kind"))
        reported_unit = _string(value.get("unit"))
        is_histogram_rate = metric_kind == "histogram_count" and reported_unit == "reported_unit/second"
        if is_histogram_rate:
            unit = "observations/s"
            statistic = "histogram_observation_rate"
        else:
            unit = (
                reported_unit
                if reported_unit and not reported_unit.startswith("reported_unit")
                and reported_unit != "unknown"
                else None
            )
            statistic = "histogram_observation_count" if metric_kind == "histogram_count" else "value"
        if change in {"appeared", "disappeared"}:
            baseline, incident = _number(value.get("baseline_value")), _number(value.get("incident_value"))
        else:
            baseline, incident = _pair(value, "baseline_value", "incident_value")
        if is_histogram_rate and metric == "rpc_server_call_duration_seconds_count":
            title = f"{owner} · RPC server requests"
        elif metric_kind == "histogram_count":
            title = f"{owner} · Histogram observations"
        else:
            title = f"{owner} · {_label(metric)}" if metric else f"{owner} · metric observation"
        technical = {"metric": metric, "metric_kind": metric_kind, "reported_unit": reported_unit}
        return _base(fact, signal, title, value, statistic_kind=statistic,
                     baseline=baseline, incident=incident, unit=unit,
                     technical={"field": fact.field,
                                "entity": {"type": fact.entity.type, "id": fact.entity.id},
                                "source_ref": fact.source_ref, "source_path": fact.source_path,
                                "lane": value.get("lane"), **technical})

    if signal == "log":
        severity = _string(value.get("severity"))
        baseline, incident = _pair(value, "baseline_count", "incident_count")
        title = f"{owner}{f' {severity}' if severity else ''} log pattern"
        return _base(fact, signal, title, value, statistic_kind="occurrences" if baseline is not None else None,
                     baseline=baseline, incident=incident,
                     unit="occurrences" if baseline is not None else None,
                     severity=severity, preview=_string(value.get("example")) or _string(value.get("pattern")))

    if signal == "trace":
        kind = _string(value.get("kind"))
        raw_operation = _string(value.get("operation_or_callee"))
        destination = raw_operation if kind == "edge" else None
        operation = None
        if kind == "operation" and raw_operation:
            # This is a display name for the observed operation, not an inferred edge.
            operation = raw_operation.rsplit("/", 1)[-1] if "/" in raw_operation else raw_operation
        if destination:
            title = f"{owner} → {_label(destination)} · trace latency"
        else:
            title = f"{owner} · {operation or 'trace operation'} latency"
        median = _pair(value, "baseline_median_ms", "incident_median_ms")
        mean = _pair(value, "baseline_mean_ms", "incident_mean_ms")
        baseline, incident = median if median[0] is not None else mean
        statistic = "median_latency" if median[0] is not None else "average_latency" if mean[0] is not None else None
        return _base(fact, signal, title, value, statistic_kind=statistic,
                     baseline=baseline, incident=incident, unit="ms" if statistic else None,
                     destination_service=destination, operation=operation,
                     technical={**_base(fact, signal, title, value).technical,
                                "raw_operation": raw_operation, "kind": kind})

    if signal == "kubernetes":
        resource = _string(value.get("deployment")) or _string(value.get("pod")) or fact.entity.id
        phase = _string(value.get("phase"))
        state = phase or _string(value.get("container_state")) or _string(value.get("waiting_reason"))
        title = f"{_label(resource)} · {state or 'Kubernetes observation'}"
        return _base(fact, signal, title, value, state=state,
                     technical={**_base(fact, signal, title, value).technical,
                                "pod": value.get("pod"), "container": value.get("container")})

    return _base(fact, signal, f"{owner} · {_label(fact.field)}", value)
