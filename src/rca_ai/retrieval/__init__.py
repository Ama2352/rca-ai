"""Deterministic local retrieval for historical precedent and domain knowledge."""

from rca_ai.retrieval.history import HistoryRetrievalResult, retrieve_history
from rca_ai.retrieval.knowledge import KnowledgeRetrievalResult, retrieve_knowledge
from rca_ai.retrieval.projection import RetrievalProjection, project_retrieval

__all__ = [
    "HistoryRetrievalResult",
    "KnowledgeRetrievalResult",
    "RetrievalProjection",
    "retrieve_history",
    "retrieve_knowledge",
    "project_retrieval",
]
