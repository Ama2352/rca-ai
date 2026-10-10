"""Shared canonical query rendering for History and Knowledge retrieval."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from typing import Any


_SEMANTIC_METRIC_LABELS = frozenset({
    "operation", "status", "status_code", "error", "direction", "method",
    "http_request_method", "http_response_status_code", "rpc_method",
})
_BARE = re.compile(r"^[A-Za-z0-9_./:+-]+$")


def _value(value: object) -> str:
    compact = " ".join(str(value).split())
    return compact if _BARE.fullmatch(compact) else json.dumps(compact, ensure_ascii=False)


def _line(kind: str, fields) -> str:
    return " ".join([kind] + [f"{key}={_value(value)}" for key, value in fields if value is not None and value != ""])


def _number(value: float | None) -> str | None:
    return None if value is None else f"{value:.2g}"


def _direction(change: float | None, before: object | None = None, during: object | None = None) -> str | None:
    if before is None and during is not None:
        return "appeared"
    if before is not None and during is None:
        return "disappeared"
    if change is None:
        return None
    return "increased" if change > 0 else "decreased" if change < 0 else "unchanged"


def _metric_query(fact: Mapping[str, Any]) -> str:
    labels = fact["labels"]
    fields = [
        ("lane", fact["lane"]), ("service", fact["service"]), ("metric", fact["metric"]),
        ("type", fact["metric_kind"]),
        ("direction", _direction(fact["signed_change"], fact["baseline_value"], fact["incident_value"])),
        ("unit", fact["unit"]),
    ]
    fields.extend((f"label.{key}", labels[key]) for key in sorted(_SEMANTIC_METRIC_LABELS & labels.keys()))
    fields.extend((("before", _number(fact["baseline_value"])), ("incident", _number(fact["incident_value"]))))
    if "insufficient_rate_support" in fact.get("uncertainty", ()):
        fields.append(("support", f"{fact['baseline_n']}/{fact['incident_n']}"))
    return _line("METRIC", fields)


def _log_query(fact: Mapping[str, Any]) -> str:
    direction = (
        "appeared" if fact["baseline_count"] == 0 and fact["incident_count"] > 0 else
        "disappeared" if fact["incident_count"] == 0 and fact["baseline_count"] > 0 else
        _direction(fact["signed_rate_change"])
    )
    return _line("LOG", (("lane", fact["lane"]), ("service", fact["service"]),
                          ("severity", fact["severity"]), ("pattern", fact["pattern"]), ("change", direction)))


def _trace_query(fact: Mapping[str, Any]) -> str:
    identity = "callee" if fact["kind"] == "edge" else "operation"
    error = (
        None if fact["boundary_error"] is None else "present" if fact["boundary_error"] else "absent"
    ) if fact["lane"] == "trace.boundary" else _direction(fact["error_rate_delta"])
    latency = _direction(fact["signed_latency_change_ms"], fact["baseline_mean_ms"], fact["incident_mean_ms"])
    return _line("TRACE", (("lane", fact["lane"]), ("kind", fact["kind"]), ("service", fact["service"]),
                            (identity, fact["operation_or_callee"]), ("error", error),
                            ("latency", latency),
                            ("attribution", "boundary_crossing" if fact["lane"] == "trace.boundary" else None)))


def _kubernetes_query(fact: Mapping[str, Any]) -> str:
    replicas = (
        f"{fact['ready_replicas']}/{fact['desired_replicas']}"
        if fact["ready_replicas"] is not None and fact["desired_replicas"] is not None else None
    )
    ready = str(fact["ready"]).lower() if fact["ready"] is not None else None
    return _line("KUBERNETES", (("lane", fact["lane"]), ("workload", fact["deployment"]),
                                 ("container", fact["container"]), ("phase", fact["phase"]),
                                 ("ready", ready), ("state", fact["container_state"]),
                                 ("reason", fact["waiting_reason"]), ("termination_reason", fact["termination_reason"]),
                                 ("exit_code", fact["exit_code"]), ("event", fact["event_reason"]),
                                 ("replicas", replicas)))


def build_retrieval_query(payload: Mapping[str, Any]) -> str:
    """Render the frozen normalized IncidentEvidence retrieval query.

    This accepts the already normalized retrieval payload; it does not invoke
    raw telemetry adapters or change the Fact View.
    """

    if not isinstance(payload, Mapping):
        raise TypeError("retrieval_projection must be a structured mapping")
    if not isinstance(payload.get("window"), Mapping):
        raise ValueError("IncidentEvidence.window must be an object")
    renderers = (
        ("metrics", _metric_query, lambda row: (row["lane"], row["service"], row["metric"], row["metric_kind"],
            tuple((key, str(row["labels"][key])) for key in sorted(_SEMANTIC_METRIC_LABELS & row["labels"].keys())))),
        ("logs", _log_query, lambda row: (row["lane"], row["service"], row["severity"], row["pattern"])),
        ("traces", _trace_query, lambda row: (row["lane"], row["kind"], row["service"], row["operation_or_callee"])),
        ("kubernetes", _kubernetes_query, lambda row: (row["lane"], row["deployment"], row["container"], row["phase"],
            row["container_state"], row["waiting_reason"] or "", row["termination_reason"] or "", row["event_reason"] or "")),
    )
    lines: list[str] = []
    for modality, render, identity in renderers:
        rows = payload.get(modality, ())
        if not isinstance(rows, (list, tuple)):
            raise ValueError(f"IncidentEvidence.{modality} must be an array")
        projected = []
        for row in rows:
            if not isinstance(row, Mapping):
                raise ValueError(f"IncidentEvidence.{modality} items must be objects")
            if modality == "logs":
                eligible = row.get("retrieval_eligible")
                if not isinstance(eligible, bool):
                    raise ValueError("v1.1 log retrieval eligibility metadata is required")
                if not eligible:
                    continue
            projected.append((row["lane"], identity(row), render(row)))
        lines.extend(rendered for _, _, rendered in sorted(projected))
    return "\n".join(lines) + ("\n" if lines else "")
