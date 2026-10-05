"""Pure deterministic assembly and namespace-specific source resolution.

Assembly copies already-validated text and references into the public result;
it never asks an LLM to rewrite claims after their provenance was checked.
Only Validator-approved F references populate Evidence. H and K references
remain in their own fields, and unknown or cross-store identifiers fail closed.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence

from rca_ai.domain.enums import Decision, SupportLevel
from rca_ai.domain.models import (
    CandidateAnalysis,
    CandidateHypothesis,
    CandidateResult,
    Fact,
    HistoricalContext,
    Hypothesis,
    KnowledgeItem,
    RCAResult,
    ValidationResult,
    to_dict,
)
from rca_ai.retrieval.history import HistoryRetrievalResult
from rca_ai.retrieval.knowledge import KnowledgeRetrievalResult


HistoryInput = Sequence[HistoricalContext] | HistoryRetrievalResult
KnowledgeInput = Sequence[KnowledgeItem] | KnowledgeRetrievalResult


def _history_items(history: HistoryInput) -> tuple[HistoricalContext, ...]:
    return history.items if isinstance(history, HistoryRetrievalResult) else tuple(history)


def _knowledge_items(knowledge: KnowledgeInput) -> tuple[KnowledgeItem, ...]:
    return knowledge.items if isinstance(knowledge, KnowledgeRetrievalResult) else tuple(knowledge)


def _history_source_rows(history: HistoryInput) -> dict[str, dict[str, object]]:
    items = _history_items(history)
    ranking = {}
    if isinstance(history, HistoryRetrievalResult) and history.strategy == "plain_bm25":
        ranking = {
            row["incident_id"]: (row["rank"], row["bm25_score"])
            for row in history.metadata.get("ranked", ())
        }
    result = {}
    for item in items:
        row: dict[str, object] = {
            "alias": item.alias,
            "source_id": item.source_id,
            "source_type": item.source_type,
        }
        if isinstance(history, HistoryRetrievalResult) and history.strategy == "plain_bm25":
            rank, score = ranking[item.source_id]
            row["retrieval_rank"] = rank
            row["bm25_score"] = score
        row["record"] = item.record
        result[item.alias] = to_dict(row)
    return result


def _knowledge_source_rows(knowledge: KnowledgeInput) -> dict[str, dict[str, object]]:
    items = _knowledge_items(knowledge)
    ranking = {}
    if isinstance(knowledge, KnowledgeRetrievalResult):
        ranking = {
            source_id: (rank, score)
            for rank, (source_id, score) in enumerate(knowledge.ranking, 1)
        }
    result = {}
    for item in items:
        row: dict[str, object] = {
            "alias": item.alias,
            "source_id": item.source_id,
            "source_type": item.source_type,
        }
        if isinstance(knowledge, KnowledgeRetrievalResult):
            rank, score = ranking[item.source_id]
            row["retrieval_rank"] = rank
            row["bm25_score"] = score
        row["record"] = item.record
        result[item.alias] = to_dict(row)
    return result


def _index(items: Iterable[object], key: str, expected_type: str | None = None) -> dict[str, object]:
    """Index one typed provenance store and reject duplicate/wrong-role sources."""

    result: dict[str, object] = {}
    for item in items:
        ref = getattr(item, key)
        if ref in result or (expected_type is not None and getattr(item, "source_type") != expected_type):
            raise ValueError(f"Invalid or duplicate source: {ref}")
        result[ref] = item
    return result


def _source_indexes(
    facts: Sequence[Fact],
    history: HistoryInput,
    knowledge: KnowledgeInput,
) -> tuple[dict[str, object], dict[str, object], dict[str, object]]:
    fact_index = _index(facts, "fact_id")
    history_index = _index(history, "alias", "HISTORY")
    knowledge_index = _index(knowledge, "alias", "DOMAIN_KNOWLEDGE")
    if set(fact_index) & (set(history_index) | set(knowledge_index)) or set(history_index) & set(knowledge_index):
        raise ValueError("Source IDs overlap across provenance classes")
    return fact_index, history_index, knowledge_index


def _check_refs(refs: Sequence[str], known: Mapping[str, object], label: str) -> None:
    """Require unique references to exist in the single designated store."""

    if len(refs) != len(set(refs)) or not set(refs) <= set(known):
        raise ValueError(f"Invalid {label} references")


def _validate_candidate_sources(
    hypothesis: Hypothesis,
    validation: ValidationResult,
    fact_index: Mapping[str, object],
    history_index: Mapping[str, object],
    knowledge_index: Mapping[str, object],
) -> None:
    for field, refs in (
        ("explains_fact_refs", hypothesis.explains_fact_refs),
        ("supporting_fact_refs", hypothesis.supporting_fact_refs),
    ):
        _check_refs(refs, fact_index, field)
    _check_refs(hypothesis.history_refs, history_index, "history")
    _check_refs(hypothesis.knowledge_refs, knowledge_index, "domain knowledge")
    _check_refs(validation.incident_basis.evidence, fact_index, "incident basis evidence")
    for item in validation.hard_violations + validation.qualifications:
        _check_refs(item.fact_refs, fact_index, "validator fact")
    _check_refs(validation.relation_assessment.fact_refs, fact_index, "relation fact")
    if not isinstance(validation.decision, Decision):
        raise ValueError("Invalid validator decision")
    if not isinstance(validation.support_level, SupportLevel):
        raise ValueError("Invalid validator support")
    if not isinstance(validation.relation_assessment.support_level, SupportLevel):
        raise ValueError("Invalid relation support")


def assemble_result(
    incident_id: str,
    hypotheses: Sequence[Hypothesis],
    validations: Sequence[ValidationResult],
    facts: Sequence[Fact],
    history: Sequence[HistoricalContext],
    knowledge: Sequence[KnowledgeItem],
) -> RCAResult:
    """Assemble retained candidates in Generator order, without semantic edits.

    Validations are keyed by the exact candidate ID rather than positional zip.
    Rejecting mismatched or missing entries avoids silently attaching one
    candidate's qualification/evidence to another. Empty input or all rejected
    candidates yields the frozen empty-candidate abstention result.
    """

    history_items = _history_items(history)
    knowledge_items = _knowledge_items(knowledge)
    fact_index, history_index, knowledge_index = _source_indexes(facts, history_items, knowledge_items)
    hypotheses_by_id: dict[str, Hypothesis] = {}
    for hypothesis in hypotheses:
        if hypothesis.id in hypotheses_by_id:
            raise ValueError(f"Duplicate hypothesis ID: {hypothesis.id}")
        hypotheses_by_id[hypothesis.id] = hypothesis

    validations_by_id: dict[str, ValidationResult] = {}
    for validation in validations:
        if validation.hypothesis_id in validations_by_id:
            raise ValueError(f"Duplicate validation for hypothesis: {validation.hypothesis_id}")
        if validation.hypothesis_id not in hypotheses_by_id:
            raise ValueError(f"Unknown validation hypothesis: {validation.hypothesis_id}")
        validations_by_id[validation.hypothesis_id] = validation
    if set(validations_by_id) != set(hypotheses_by_id):
        raise ValueError("Missing or mismatched validation")

    candidate_results: list[CandidateResult] = []
    for hypothesis in hypotheses:
        validation = validations_by_id[hypothesis.id]
        if validation.hypothesis_id != hypothesis.id:
            raise ValueError("Missing or mismatched validation")
        _validate_candidate_sources(
            hypothesis, validation, fact_index, history_index, knowledge_index
        )
        if validation.decision is Decision.REJECT:
            continue
        candidate_results.append(CandidateResult(
            incident_id=incident_id,
            analysis=CandidateAnalysis(
                decision=validation.decision,
                support_level=validation.support_level,
            ),
            hypothesis=CandidateHypothesis(
                id=hypothesis.id,
                explanation=hypothesis.explanation,
                assumptions=hypothesis.assumptions,
                unresolved=hypothesis.unresolved,
            ),
            evidence_refs=validation.incident_basis.evidence,
            history_refs=hypothesis.history_refs,
            knowledge_refs=hypothesis.knowledge_refs,
            qualifications=validation.qualifications,
            validation_unresolved=validation.unresolved,
        ))
    return RCAResult(incident_id=incident_id, candidate_results=tuple(candidate_results))


def resolve_sources(
    candidate: CandidateResult,
    facts: Sequence[Fact],
    history: HistoryInput,
    knowledge: KnowledgeInput,
) -> dict[str, list[dict[str, object]]]:
    """Dereference candidate refs only within their original F/H/K stores.

    Source resolution is intentionally a pure lookup. A miss in one namespace
    is an error; searching another store could misrepresent provenance.
    """

    history_items = _history_items(history)
    knowledge_items = _knowledge_items(knowledge)
    fact_index, history_index, knowledge_index = _source_indexes(facts, history_items, knowledge_items)
    history_rows = _history_source_rows(history)
    knowledge_rows = _knowledge_source_rows(knowledge)
    _check_refs(candidate.evidence_refs, fact_index, "evidence")
    _check_refs(candidate.history_refs, history_index, "history")
    _check_refs(candidate.knowledge_refs, knowledge_index, "domain knowledge")
    return {
        "evidence": [to_dict(fact_index[ref]) for ref in candidate.evidence_refs],
        "history": [history_rows[ref] for ref in candidate.history_refs],
        "domain_knowledge": [knowledge_rows[ref] for ref in candidate.knowledge_refs],
    }
