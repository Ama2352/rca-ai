"""Frozen channel-based History retrieval; returned records remain H precedent."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
from pathlib import Path
import re
from collections.abc import Mapping
from typing import Any

from rca_ai.domain.models import HistoricalContext
from rca_ai.retrieval._bm25 import BM25Index
from rca_ai.retrieval._channels import CHANNELS, fuse, render_channels


_PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_HISTORY_PATH = _PROJECT_ROOT / "data" / "history" / "historical_incidents.jsonl"
_SEMANTIC_METRIC_LABELS = frozenset({
    "operation", "status", "status_code", "error", "direction", "method",
    "http_request_method", "http_response_status_code", "rpc_method",
})
_BARE = re.compile(r"^[A-Za-z0-9_./:+-]+$")


@dataclass(frozen=True)
class HistoryRetrievalResult:
    """History candidates plus exact query/ranking diagnostics for audit."""

    query: str
    strategy: str
    items: tuple[HistoricalContext, ...]
    metadata: Mapping[str, Any]


def load_history_store(path: Path = DEFAULT_HISTORY_PATH) -> tuple[Mapping[str, Any], ...]:
    """Load the frozen JSONL corpus in byte-source order and verify its manifest."""

    raw = path.read_bytes()
    manifest_path = path.with_name("corpus_freeze_manifest.json")
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        expected_hash = manifest.get("corpus_sha256")
        if expected_hash and hashlib.sha256(raw).hexdigest() != expected_hash:
            raise ValueError("Historical corpus does not match its freeze manifest")
    rows = tuple(json.loads(line) for line in raw.decode("utf-8").splitlines() if line.strip())
    ids = [str(row["incident_id"]) for row in rows]
    if len(set(ids)) != len(ids):
        raise ValueError("Historical incident IDs must be unique")
    if any("retrieval_text" not in row for row in rows):
        raise ValueError("Historical corpus record lacks retrieval_text")
    return rows


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


def _canonical_query(payload: Mapping[str, Any]) -> str:
    """Port the frozen normalized IncidentEvidence-to-query projection.

    This accepts the already normalized retrieval payload; it does not invoke
    raw telemetry adapters or change the Fact View.
    """

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


def _make_context(alias: str, record: Mapping[str, Any]) -> HistoricalContext:
    return HistoricalContext(alias=alias, source_id=str(record["incident_id"]), record=record)


def _resolution_context(row: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "incident_id": str(row["incident_id"]),
        "historical_evidence": str(row["retrieval_text"]),
        "root_cause": str(row.get("root_cause") or ""),
        "affected_component": str(row.get("affected_component") or ""),
        "recommended_action": str(row.get("recommended_action") or ""),
        "resolution_note": str(row.get("resolution_note") or ""),
    }


def _channel_retrieval(query: str, corpus: tuple[Mapping[str, Any], ...]) -> tuple[tuple[HistoricalContext, ...], dict[str, Any]]:
    query_views = render_channels(query)
    history_views = {str(row["incident_id"]): render_channels(str(row["retrieval_text"])) for row in corpus}
    active = [channel for channel in CHANNELS if query_views[channel].strip()]
    channel_results: dict[str, list[dict[str, Any]]] = {}
    for channel in active:
        documents = {key: views[channel] for key, views in history_views.items() if views[channel].strip()}
        ranked = BM25Index(documents, k1=1.5, b=0.75).rank(query_views[channel], k=len(documents))
        hits = [(key, score) for key, score in ranked if score > 0][:10]
        channel_results[channel.lower()] = [
            {"rank": rank, "incident_id": key, "bm25_score": float(score)}
            for rank, (key, score) in enumerate(hits, 1)
        ]
    fused = fuse(channel_results, k=60)
    top_ids = [row["incident_id"] for row in fused[:3]]
    records_by_id = {str(row["incident_id"]): row for row in corpus}
    diagnostics = {
        "active_modalities": [channel.lower() for channel in active],
        "channels": {
            channel.lower(): {"query_view": query_views[channel], "top10": channel_results.get(channel.lower(), [])}
            for channel in CHANNELS if channel in active
        },
        "rrf_ranking": fused,
        "final_top3": top_ids,
    }
    items = tuple(_make_context(f"H{index}", _resolution_context(records_by_id[key])) for index, key in enumerate(top_ids, 1))
    return items, diagnostics


def retrieve_history(retrieval_projection: Mapping[str, Any], store: Path = DEFAULT_HISTORY_PATH) -> HistoryRetrievalResult:
    """Retrieve H precedent from the structured RCA retrieval projection.

    Requiring the projection object prevents caller representation from
    selecting an algorithm. Every canonical incident uses the same channel
    BM25 and RRF path.
    """
    if not isinstance(retrieval_projection, Mapping):
        raise TypeError("retrieval_projection must be a structured mapping")
    corpus = load_history_store(store)
    query = _canonical_query(retrieval_projection)
    items, diagnostics = _channel_retrieval(query, corpus)
    return HistoryRetrievalResult(query, "channel_bm25_rrf", items, {"diagnostics": diagnostics})


def _query_for_retrieval_projection(retrieval_projection: Mapping[str, Any]) -> str:
    if not isinstance(retrieval_projection, Mapping):
        raise TypeError("retrieval_projection must be a structured mapping")
    return _canonical_query(retrieval_projection)
