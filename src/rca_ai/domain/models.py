"""Source-aware internal contracts for the frozen RCA pipeline.

These models describe data boundaries; they do not perform retrieval, infer
causes, or turn context into current-incident evidence. Nested JSON values are
kept in their source shape and are treated as read-only by convention. Frozen
dataclasses prevent rebinding model fields, while deliberately avoiding a
custom deep-immutable container layer.
"""

from dataclasses import dataclass, field, fields, is_dataclass
from enum import Enum
from typing import Any, Mapping

from rca_ai.domain.enums import Decision, SupportLevel


@dataclass(frozen=True)
class IncidentInput:
    """Thin demo-boundary envelope around a source-faithful normalized payload.

    The three frozen fixtures have different normalized shapes, so this model
    keeps their payload opaque. A separate retrieval input is optional because
    some frozen retrieval paths consume a query representation distinct from
    the normalized evidence. Neither field is semantically rewritten here.
    """

    incident_id: str
    normalized_evidence: Mapping[str, Any]
    retrieval_input: Mapping[str, Any] | str | None = None


@dataclass(frozen=True)
class FactEntity:
    """Identity of the exact entity to which a normalized Fact belongs."""

    type: str
    id: str


@dataclass(frozen=True)
class Fact:
    """Immutable source-faithful observation for the current incident.

    A Fact contains only the normalized entity, field, exact value, and source
    provenance. It must never contain a generated cause, semantic summary,
    confidence, or explanation; those belong to the Hypothesis layer. The
    frozen dataclass prevents field rebinding. Nested JSON values are retained
    as supplied and are read-only by convention rather than deeply wrapped.
    """

    fact_id: str
    entity: FactEntity
    field: str
    value: Any
    source_ref: str
    source_path: str


@dataclass(frozen=True)
class HistoricalContext:
    """A retrieved historical record, kept in the precedent-only H namespace.

    ``record`` preserves the corpus record's exact fields. Keeping it as a
    mapping accommodates incident-specific historical records without
    promoting any of them to current Facts.
    """

    alias: str
    source_id: str
    source_type: str = field(default="HISTORY", init=False)
    record: Mapping[str, Any]


@dataclass(frozen=True)
class KnowledgeItem:
    """A sourced general-knowledge record, kept separate from current Facts.

    ``record`` retains the frozen store's knowledge key, claim, and source
    provenance without rewriting the source into incident-specific evidence.
    """

    alias: str
    source_id: str
    source_type: str = field(default="DOMAIN_KNOWLEDGE", init=False)
    record: Mapping[str, Any]


@dataclass(frozen=True)
class Hypothesis:
    """Generated explanatory proposal with separate F, H, and K references.

    This is inference, not observed Evidence. Its wording may be speculative;
    the Validator later decides whether to keep or qualify it without changing
    the immutable Facts it references.
    """

    id: str
    explanation: str
    explains_fact_refs: tuple[str, ...]
    supporting_fact_refs: tuple[str, ...]
    history_refs: tuple[str, ...]
    knowledge_refs: tuple[str, ...]
    assumptions: tuple[str, ...]
    unresolved: tuple[str, ...]


@dataclass(frozen=True)
class Qualification:
    """Validator qualification kept apart from both Facts and H wording."""

    claim: str
    issue: str
    fact_refs: tuple[str, ...]
    observed_form: str


@dataclass(frozen=True)
class HardViolation:
    """Validator-reported material conflict or fabricated factual claim."""

    claim: str
    type: str
    fact_refs: tuple[str, ...]
    reason: str


@dataclass(frozen=True)
class IncidentBasis:
    """Compact current-evidence basis from the effective Validator contract."""

    evidence: tuple[str, ...]


@dataclass(frozen=True)
class RelationAssessment:
    """Validator assessment of the candidate's explanatory relation."""

    relation: str
    support_level: SupportLevel
    fact_refs: tuple[str, ...]
    reason: str


@dataclass(frozen=True)
class ValidationResult:
    """Frozen Validator output; decision and support remain independent."""

    hypothesis_id: str
    decision: Decision
    support_level: SupportLevel
    incident_basis: IncidentBasis
    hard_violations: tuple[HardViolation, ...]
    qualifications: tuple[Qualification, ...]
    relation_assessment: RelationAssessment
    unresolved: tuple[str, ...]


@dataclass(frozen=True)
class CandidateAnalysis:
    """Decision/support pair carried into one retained final candidate."""

    decision: Decision
    support_level: SupportLevel


@dataclass(frozen=True)
class CandidateHypothesis:
    """The unrewritten H fields exposed for a retained API/UI candidate."""

    id: str
    explanation: str
    assumptions: tuple[str, ...]
    unresolved: tuple[str, ...]


@dataclass(frozen=True)
class CandidateResult:
    """One assembled candidate with explicitly separated provenance refs."""

    incident_id: str
    analysis: CandidateAnalysis
    hypothesis: CandidateHypothesis
    evidence_refs: tuple[str, ...]
    history_refs: tuple[str, ...]
    knowledge_refs: tuple[str, ...]
    qualifications: tuple[Qualification, ...]
    validation_unresolved: tuple[str, ...]


@dataclass(frozen=True)
class RCAResult:
    """API/UI-ready assembled result; an empty candidate tuple means abstention."""

    incident_id: str
    candidate_results: tuple[CandidateResult, ...]


def to_dict(value: Any) -> Any:
    """Convert domain dataclasses/enums/collections to deterministic JSON data.

    This small adapter preserves field names and enum string values. It does
    not create display text or merge the F/H/K namespaces.
    """

    if isinstance(value, Enum):
        return value.value
    if is_dataclass(value) and not isinstance(value, type):
        return {item.name: to_dict(getattr(value, item.name)) for item in fields(value)}
    if isinstance(value, Mapping):
        if not all(isinstance(key, str) for key in value):
            raise TypeError("JSON object keys must be strings")
        return {key: to_dict(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [to_dict(item) for item in value]
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    raise TypeError(f"Value of type {type(value).__name__} is not JSON-compatible")
