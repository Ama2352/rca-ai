"""Frozen request construction and structural validation for H generation.

Facts are serialized as exact current observations; retrieved History and
Knowledge stay in distinct context lists. The model may propose explanations,
but this boundary neither creates facts nor judges causal correctness.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
import json
from typing import Any, Protocol

import jsonschema

from rca_ai.domain.models import Fact, HistoricalContext, Hypothesis, KnowledgeItem
from rca_ai.providers.groq import ProviderResult
from rca_ai.reasoning.prompts import GENERATOR_SYSTEM_PROMPT
from rca_ai.reasoning.schemas import GENERATOR_JSON_SCHEMA, GENERATOR_SCHEMA_NAME
from rca_ai.retrieval.history import HistoryRetrievalResult
from rca_ai.retrieval.knowledge import KnowledgeRetrievalResult


GENERATOR_MODEL = "openai/gpt-oss-120b"
GENERATOR_REASONING_EFFORT = "medium"
GENERATOR_INCLUDE_REASONING = False
GENERATOR_TEMPERATURE = 0
GENERATOR_MAX_COMPLETION_TOKENS = 4096


class JsonCompletionProvider(Protocol):
    """Transport interface shared by semantic stages; provider errors propagate."""

    def complete(self, request: Mapping[str, Any]) -> ProviderResult: ...


class GenerationValidationError(ValueError):
    """A completed provider JSON response violates the frozen H contract."""


@dataclass(frozen=True)
class GenerationResult:
    """Validated hypotheses plus operational request/response audit material."""

    hypotheses: tuple[Hypothesis, ...]
    request: Mapping[str, Any]
    provider_result: ProviderResult


def _fact_payload(fact: Fact) -> dict[str, Any]:
    """Serialize only the frozen Fact fields, retaining projection field order.

    The final runner's composite normalized shape emitted entity before source
    provenance, while the two other supported projections emitted source first.
    This is a representation detail of those existing structural contracts,
    not scenario-specific semantic routing.
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


def _history_payload(result: HistoryRetrievalResult) -> list[dict[str, Any]]:
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


def _knowledge_payload(result: KnowledgeRetrievalResult) -> list[dict[str, Any]]:
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


def build_generator_request(
    facts: Sequence[Fact],
    history: HistoryRetrievalResult,
    knowledge: KnowledgeRetrievalResult,
) -> dict[str, Any]:
    """Build the exact frozen Groq request from selected Facts and fresh H/K.

    Operational ranking metadata is added only where the final request carried
    it. The F/H/K aliases, records, values, and provenance remain unchanged.
    """

    user_payload = {
        "current_facts": [_fact_payload(fact) for fact in facts],
        "history": _history_payload(history),
        "domain_knowledge": _knowledge_payload(knowledge),
    }
    user_message = json.dumps(user_payload, ensure_ascii=False, separators=(",", ":"))
    return {
        "model": GENERATOR_MODEL,
        "reasoning_effort": GENERATOR_REASONING_EFFORT,
        "temperature": GENERATOR_TEMPERATURE,
        "max_completion_tokens": GENERATOR_MAX_COMPLETION_TOKENS,
        "messages": [
            {"role": "system", "content": GENERATOR_SYSTEM_PROMPT},
            {"role": "user", "content": user_message},
        ],
        "response_format": {
            "type": "json_schema",
            "json_schema": {
                "name": GENERATOR_SCHEMA_NAME,
                "strict": True,
                "schema": GENERATOR_JSON_SCHEMA,
            },
        },
        "include_reasoning": GENERATOR_INCLUDE_REASONING,
    }


def validate_generation(
    result: Any,
    facts: Sequence[Fact],
    history: Sequence[HistoricalContext],
    knowledge: Sequence[KnowledgeItem],
) -> tuple[Hypothesis, ...]:
    """Apply only the frozen schema, count, identity, and reference checks.

    These structural checks prevent unknown provenance references from being
    accepted. They intentionally do not evaluate whether an explanation is
    causally plausible; that is outside the Generator contract.
    """

    try:
        jsonschema.validate(result, GENERATOR_JSON_SCHEMA)
    except jsonschema.ValidationError as exc:
        raise GenerationValidationError(f"Generator output does not match schema: {exc.message}") from exc
    except (TypeError, jsonschema.SchemaError) as exc:
        raise GenerationValidationError(f"Generator output cannot be schema-validated: {exc}") from exc

    rows = result["hypotheses"]
    if len(rows) > 3 or len({row["id"] for row in rows}) != len(rows):
        raise GenerationValidationError("Invalid hypothesis count or duplicate IDs")

    known = {
        "explains_fact_refs": {fact.fact_id for fact in facts},
        "supporting_fact_refs": {fact.fact_id for fact in facts},
        "history_refs": {item.alias for item in history},
        "knowledge_refs": {item.alias for item in knowledge},
    }
    hypotheses: list[Hypothesis] = []
    for row in rows:
        if len(row["assumptions"]) > 3 or len(row["unresolved"]) > 3:
            raise GenerationValidationError("Hypothesis exceeds frozen limits")
        for field, allowed in known.items():
            refs = row[field]
            if len(refs) != len(set(refs)) or not set(refs) <= allowed:
                raise GenerationValidationError(f"Invalid {field} references")
        hypotheses.append(Hypothesis(
            id=row["id"],
            explanation=row["explanation"],
            explains_fact_refs=tuple(row["explains_fact_refs"]),
            supporting_fact_refs=tuple(row["supporting_fact_refs"]),
            history_refs=tuple(row["history_refs"]),
            knowledge_refs=tuple(row["knowledge_refs"]),
            assumptions=tuple(row["assumptions"]),
            unresolved=tuple(row["unresolved"]),
        ))
    return tuple(hypotheses)


class HypothesisGenerator:
    """Request one frozen candidate-generation completion via an injected provider."""

    def __init__(self, provider: JsonCompletionProvider) -> None:
        self._provider = provider

    def generate(
        self,
        facts: Sequence[Fact],
        history: HistoryRetrievalResult,
        knowledge: KnowledgeRetrievalResult,
    ) -> GenerationResult:
        request = build_generator_request(facts, history, knowledge)
        response = self._provider.complete(request)
        hypotheses = validate_generation(
            response.content, facts, history.items, knowledge.items
        )
        return GenerationResult(hypotheses, request, response)
