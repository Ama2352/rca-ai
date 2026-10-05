"""Typed domain contracts for the source-faithful RCA pipeline."""

from rca_ai.domain.enums import Decision, SupportLevel
from rca_ai.domain.models import (
    CandidateAnalysis,
    CandidateHypothesis,
    CandidateResult,
    Fact,
    FactEntity,
    HardViolation,
    HistoricalContext,
    Hypothesis,
    IncidentBasis,
    IncidentInput,
    KnowledgeItem,
    Qualification,
    RCAResult,
    RelationAssessment,
    ValidationResult,
    to_dict,
)

__all__ = [
    "CandidateAnalysis",
    "CandidateHypothesis",
    "CandidateResult",
    "Decision",
    "Fact",
    "FactEntity",
    "HardViolation",
    "HistoricalContext",
    "Hypothesis",
    "IncidentBasis",
    "IncidentInput",
    "KnowledgeItem",
    "Qualification",
    "RCAResult",
    "RelationAssessment",
    "SupportLevel",
    "ValidationResult",
    "to_dict",
]
