"""Deterministic current-Fact construction and input-budget selection."""

from rca_ai.facts.builder import build_fact_view, verify_fact_view
from rca_ai.facts.selector import SelectionResult, request_bytes, select_facts

__all__ = [
    "SelectionResult",
    "build_fact_view",
    "request_bytes",
    "select_facts",
    "verify_fact_view",
]
