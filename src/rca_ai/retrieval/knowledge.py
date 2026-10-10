"""Frozen BM25 retrieval for general sourced semantics in the K namespace."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from collections.abc import Mapping
from typing import Any

from rca_ai.domain.models import KnowledgeItem
from rca_ai.retrieval._bm25 import BM25Index
from rca_ai.retrieval.query import build_retrieval_query


_PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_KNOWLEDGE_PATH = _PROJECT_ROOT / "data" / "knowledge" / "knowledge.json"


@dataclass(frozen=True)
class KnowledgeRetrievalResult:
    """Positive-score K matches and complete frozen top-three rank metadata."""

    query: str
    items: tuple[KnowledgeItem, ...]
    ranking: tuple[tuple[str, float], ...]


def load_knowledge_store(path: Path = DEFAULT_KNOWLEDGE_PATH) -> tuple[Mapping[str, Any], ...]:
    """Read exact K records in source order; callers keep them in the K role."""

    rows = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(rows, list) or any(not isinstance(row, Mapping) for row in rows):
        raise ValueError("Knowledge store must be a JSON array of objects")
    if any("knowledge_key" not in row or "claim" not in row for row in rows):
        raise ValueError("Knowledge record requires knowledge_key and claim")
    return tuple(rows)


def retrieve_knowledge(
    retrieval_projection: Mapping[str, Any],
    store: Path = DEFAULT_KNOWLEDGE_PATH,
) -> KnowledgeRetrievalResult:
    """Retrieve top-three positive BM25 K items from an exact frozen query.

    K records explain general semantics only; even a positive match remains
    `KnowledgeItem` and cannot enter current incident Evidence.
    """

    query = build_retrieval_query(retrieval_projection)
    records = load_knowledge_store(store)
    indexed = {str(row["knowledge_key"]): f"{row['knowledge_key']} {row['claim']}" for row in records}
    ranking = tuple(BM25Index(indexed, k1=1.5, b=0.75).rank(query, k=3))
    by_key = {str(row["knowledge_key"]): row for row in records}
    items = tuple(
        KnowledgeItem(alias=f"K{index}", source_id=key, record=by_key[key])
        for index, (key, score) in enumerate(ranking, 1) if score > 0
    )
    return KnowledgeRetrievalResult(query=query, items=items, ranking=ranking)
