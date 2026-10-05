"""Frozen one-candidate Validator request and structural response checks.

This wrapper carries the candidate and F/H/K inputs to the model, then checks
only the effective schema, candidate identity, and current-F reference
integrity. It does not require causal proof or impose a local decision policy;
that would change the frozen qualification-oriented semantic contract.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
import json
from typing import Any

import jsonschema

from rca_ai.domain.enums import Decision, SupportLevel
from rca_ai.domain.models import (
    Fact,
    HardViolation,
    HistoricalContext,
    Hypothesis,
    IncidentBasis,
    KnowledgeItem,
    Qualification,
    RelationAssessment,
    ValidationResult,
)
from rca_ai.providers.groq import ProviderResult
from rca_ai.reasoning.generator import (
    GENERATOR_MAX_COMPLETION_TOKENS,
    GENERATOR_MODEL,
    GENERATOR_REASONING_EFFORT,
    GENERATOR_TEMPERATURE,
    JsonCompletionProvider,
    _fact_payload,
    _history_payload,
    _knowledge_payload,
)
from rca_ai.reasoning.prompts import VALIDATOR_SYSTEM_PROMPT
from rca_ai.reasoning.schemas import VALIDATOR_JSON_SCHEMA, VALIDATOR_SCHEMA_NAME
from rca_ai.retrieval.history import HistoryRetrievalResult
from rca_ai.retrieval.knowledge import KnowledgeRetrievalResult


class ValidatorValidationError(ValueError):
    """A completed Validator JSON response violates the frozen contract."""


@dataclass(frozen=True)
class ValidationExecution:
    """Validated domain result and transport artifacts, kept outside RCA semantics."""

    result: ValidationResult
    request: Mapping[str, Any]
    provider_result: ProviderResult


def _hypothesis_payload(hypothesis: Hypothesis) -> dict[str, Any]:
    """Preserve the Generator contract's candidate field names, order, and text."""

    return {
        "id": hypothesis.id,
        "explanation": hypothesis.explanation,
        "explains_fact_refs": list(hypothesis.explains_fact_refs),
        "supporting_fact_refs": list(hypothesis.supporting_fact_refs),
        "history_refs": list(hypothesis.history_refs),
        "knowledge_refs": list(hypothesis.knowledge_refs),
        "assumptions": list(hypothesis.assumptions),
        "unresolved": list(hypothesis.unresolved),
    }


def build_validator_request(
    hypothesis: Hypothesis,
    facts: Sequence[Fact],
    history: HistoryRetrievalResult,
    knowledge: KnowledgeRetrievalResult,
) -> dict[str, Any]:
    """Build one exact frozen effective Validator request for a single H.

    F remains current evidence; H and K remain separate contextual records.
    The compact incident-basis output schema is supplied as-is and does not
    promote Validator commentary or the candidate into observed Facts.
    """

    user_payload = {
        "current_facts": [_fact_payload(fact) for fact in facts],
        "history": _history_payload(history),
        "domain_knowledge": _knowledge_payload(knowledge),
        "candidate_hypothesis": _hypothesis_payload(hypothesis),
    }
    return {
        "model": GENERATOR_MODEL,
        "reasoning_effort": GENERATOR_REASONING_EFFORT,
        "include_reasoning": False,
        "temperature": GENERATOR_TEMPERATURE,
        "max_completion_tokens": GENERATOR_MAX_COMPLETION_TOKENS,
        "messages": [
            {"role": "system", "content": VALIDATOR_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": json.dumps(user_payload, ensure_ascii=False, separators=(",", ":")),
            },
        ],
        "response_format": {
            "type": "json_schema",
            "json_schema": {
                "name": VALIDATOR_SCHEMA_NAME,
                "strict": True,
                "schema": VALIDATOR_JSON_SCHEMA,
            },
        },
    }


def validate_validator_output(
    output: Any,
    hypothesis: Hypothesis,
    facts: Sequence[Fact],
) -> ValidationResult:
    """Validate the final strict schema, H identity, and exact known F refs.

    The reference check mirrors the frozen runner: the compact incident basis,
    relation assessment, hard violations, and qualifications may cite only
    current Fact IDs. This is a provenance check, not a semantic judgment.
    """

    try:
        jsonschema.validate(output, VALIDATOR_JSON_SCHEMA)
    except jsonschema.ValidationError as exc:
        raise ValidatorValidationError(f"Validator output does not match schema: {exc.message}") from exc
    except (TypeError, jsonschema.SchemaError) as exc:
        raise ValidatorValidationError(f"Validator output cannot be schema-validated: {exc}") from exc

    if output["hypothesis_id"] != hypothesis.id:
        raise ValidatorValidationError("Validator hypothesis identity mismatch")

    known = {fact.fact_id for fact in facts}
    reference_groups = [
        output["incident_basis"]["evidence"],
        output["relation_assessment"]["fact_refs"],
        *(item["fact_refs"] for item in output["hard_violations"]),
        *(item["fact_refs"] for item in output["qualifications"]),
    ]
    for refs in reference_groups:
        if len(refs) != len(set(refs)) or not set(refs) <= known:
            raise ValidatorValidationError("Validator referenced a non-current fact")

    return ValidationResult(
        hypothesis_id=output["hypothesis_id"],
        decision=Decision(output["decision"]),
        support_level=SupportLevel(output["support_level"]),
        incident_basis=IncidentBasis(tuple(output["incident_basis"]["evidence"])),
        hard_violations=tuple(
            HardViolation(
                claim=row["claim"],
                type=row["type"],
                fact_refs=tuple(row["fact_refs"]),
                reason=row["reason"],
            )
            for row in output["hard_violations"]
        ),
        qualifications=tuple(
            Qualification(
                claim=row["claim"],
                issue=row["issue"],
                fact_refs=tuple(row["fact_refs"]),
                observed_form=row["observed_form"],
            )
            for row in output["qualifications"]
        ),
        relation_assessment=RelationAssessment(
            relation=output["relation_assessment"]["relation"],
            support_level=SupportLevel(output["relation_assessment"]["support_level"]),
            fact_refs=tuple(output["relation_assessment"]["fact_refs"]),
            reason=output["relation_assessment"]["reason"],
        ),
        unresolved=tuple(output["unresolved"]),
    )


class HypothesisValidator:
    """Make one independent Validator call for one existing candidate H."""

    def __init__(self, provider: JsonCompletionProvider) -> None:
        self._provider = provider

    def validate(
        self,
        hypothesis: Hypothesis,
        facts: Sequence[Fact],
        history: HistoryRetrievalResult,
        knowledge: KnowledgeRetrievalResult,
    ) -> ValidationExecution:
        request = build_validator_request(hypothesis, facts, history, knowledge)
        response = self._provider.complete(request)
        result = validate_validator_output(response.content, hypothesis, facts)
        return ValidationExecution(result=result, request=request, provider_result=response)
