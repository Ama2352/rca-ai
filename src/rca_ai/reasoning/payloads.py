"""Shared frozen F/H/K request payload serialization."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from rca_ai.domain.models import Fact
from rca_ai.retrieval.history import HistoryRetrievalResult
from rca_ai.retrieval.knowledge import KnowledgeRetrievalResult


def fact_payload(fact: Fact) -> dict[str, Any]:
    """Serialize frozen Fact fields, retaining their two established field orders.

    The composite normalized shape places entity before provenance; the two
    prepared projections place source provenance first. This is a wire-format
    detail and does not vary by scenario.
    """

    if fact.source_path.startswith("/facts/"):
        keys = ("fact_id", "entity", "field", "value", "source_ref", "source_path")
    else:
        keys = ("fact_id", "source_ref", "entity", "field", "value", "source_path")
    row = {
        "fact_id": fact.fact_id,
        "source_ref": fact.source_ref,
        "entity": {"type": fact.entity.type, "id": fact.entity.id},
        "field": fact.field,
        "value": fact.value,
        "source_path": fact.source_path,
    }
    return {key: row[key] for key in keys}


def history_payload(result: HistoryRetrievalResult) -> list[dict[str, Any]]:
    ranked = {
        row["incident_id"]: (row["rank"], row["bm25_score"])
        for row in result.metadata.get("ranked", ())
    }
    payload = []
    for item in result.items:
        row: dict[str, Any] = {
            "alias": item.alias,
            "source_id": item.source_id,
            "source_type": item.source_type,
        }
        if result.strategy == "plain_bm25":
            rank, score = ranked[item.source_id]
            row["retrieval_rank"] = rank
            row["bm25_score"] = score
        row["record"] = item.record
        payload.append(row)
    return payload


def knowledge_payload(result: KnowledgeRetrievalResult) -> list[dict[str, Any]]:
    ranked = {source_id: (rank, score) for rank, (source_id, score) in enumerate(result.ranking, 1)}
    payload = []
    for item in result.items:
        rank, score = ranked[item.source_id]
        payload.append({
            "alias": item.alias,
            "source_id": item.source_id,
            "source_type": item.source_type,
            "retrieval_rank": rank,
            "bm25_score": score,
            "record": item.record,
        })
    return payload
