"""Deterministic local retrieval for historical precedent and domain knowledge."""

from rca_ai.retrieval.history import HistoryRetrievalResult, retrieve_history
from rca_ai.retrieval.knowledge import KnowledgeRetrievalResult, retrieve_knowledge

__all__ = [
    "HistoryRetrievalResult",
    "KnowledgeRetrievalResult",
    "retrieve_history",
    "retrieve_knowledge",
]
