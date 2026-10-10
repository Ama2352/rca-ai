"""Frozen channel-based History retrieval; returned records remain H precedent."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from collections.abc import Mapping
from typing import Any

from rca_ai.domain.models import HistoricalContext
from rca_ai.retrieval._bm25 import BM25Index
from rca_ai.retrieval._channels import CHANNELS, fuse, render_channels
from rca_ai.retrieval.query import build_retrieval_query


_PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_HISTORY_PATH = _PROJECT_ROOT / "data" / "history" / "historical_incidents.jsonl"


def _canonical_history_bytes(raw: bytes) -> bytes:
    """Normalize JSONL line endings before checking the frozen corpus digest.

    The manifest digest corresponds to CRLF-serialized JSONL. Git stores the same
    records with LF, so hashing raw checkout bytes made the freeze check depend
    on the checkout's line-ending conversion.
    """
    normalized = raw.replace(b"\r\n", b"\n").replace(b"\r", b"\n")
    return normalized.replace(b"\n", b"\r\n")


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
        canonical_raw = _canonical_history_bytes(raw)
        if expected_hash and hashlib.sha256(canonical_raw).hexdigest() != expected_hash:
            raise ValueError("Historical corpus does not match its freeze manifest")
    rows = tuple(json.loads(line) for line in raw.decode("utf-8").splitlines() if line.strip())
    ids = [str(row["incident_id"]) for row in rows]
    if len(set(ids)) != len(ids):
        raise ValueError("Historical incident IDs must be unique")
    if any("retrieval_text" not in row for row in rows):
        raise ValueError("Historical corpus record lacks retrieval_text")
    return rows


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
    query = build_retrieval_query(retrieval_projection)
    items, diagnostics = _channel_retrieval(query, corpus)
    return HistoryRetrievalResult(query, "channel_bm25_rrf", items, {"diagnostics": diagnostics})
