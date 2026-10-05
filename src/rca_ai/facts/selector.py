"""Frozen deterministic selector for whole immutable Facts.

Selection is only an input-budget operation. It ranks existing observations
using the frozen category/order policy and returns the same Fact objects; it
never derives, merges, or edits Facts. Request size uses compact UTF-8 JSON
bytes and the frozen four-bytes-per-token estimate, which is a budget heuristic
rather than an exact tokenizer.
"""

from dataclasses import dataclass
import json
import math
from types import MappingProxyType
from typing import Any, Callable, Mapping, Sequence

from rca_ai.domain.models import Fact, to_dict


_MAX_ESTIMATED_INPUT_TOKENS = 8_000
_MAX_SELECTED_ESTIMATED_TOKENS = 7_000
_MAX_FACT_INPUT_BYTES = 20_000


@dataclass(frozen=True)
class SelectionResult:
    """Selected original Facts plus only the operational metadata in the frozen run."""

    facts: tuple[Fact, ...]
    selected_ids: tuple[str, ...]
    omitted_ids: tuple[str, ...]
    selection_reasons: Mapping[str, str]
    selector_used: bool
    full_fact_count: int
    selected_fact_count: int
    full_request_bytes: int
    selected_request_bytes: int
    selected_fact_bytes: int | None


def request_bytes(request: Any) -> int:
    """Return the frozen compact UTF-8 JSON request size in bytes."""

    encoded = json.dumps(request, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return len(encoded)


def _category(fact: Fact) -> tuple[int, str]:
    """Return the exact frozen category priority and audit reason for one Fact."""

    value = fact.value
    if not isinstance(value, dict):
        return 5, "other_observation"
    labels = value.get("labels") or {}
    error_status = any(
        "ERROR" in str(labels.get(key, "")).upper()
        for key in ("status_code", "rpc_response_status_code", "error_type")
    )
    if value.get("error") == "increased" or error_status:
        return 0, "observed_error_or_failed_relation"
    if "pattern" in value and value.get("change") in {"appeared", "increased", "decreased"}:
        return 1, "changed_log_pattern"
    if value.get("change") == "appeared":
        return 2, "new_observation"
    if value.get("kind") == "edge":
        return 3, "observed_dependency_relation"
    if value.get("change") in {"increased", "decreased"}:
        return 4, "changed_metric"
    return 5, "other_observation"


def _fact_list_bytes(facts: Sequence[Fact]) -> int:
    rows = [to_dict(fact) for fact in facts]
    return len(json.dumps(rows, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))


def _select_with_budget(
    facts: tuple[Fact, ...], *, max_input_bytes: int, context_bytes: int
) -> tuple[tuple[Fact, ...], tuple[str, ...], int]:
    """Port the frozen category ordering and greedy whole-Fact byte fit."""

    if max_input_bytes <= context_bytes:
        raise ValueError("No Fact input budget remains")
    if len({fact.fact_id for fact in facts}) != len(facts):
        raise ValueError("Duplicate Fact IDs")

    ranked = sorted(enumerate(facts), key=lambda item: (_category(item[1])[0], item[0]))
    selected: list[Fact] = []
    reasons: list[str] = []
    for _, fact in ranked:
        proposed = (*selected, fact)
        if context_bytes + _fact_list_bytes(proposed) <= max_input_bytes:
            selected.append(fact)
            reasons.append(_category(fact)[1])
    if not selected:
        raise ValueError("No immutable Fact fits the input budget")
    return tuple(selected), tuple(reasons), _fact_list_bytes(selected)


def select_facts(
    facts: Sequence[Fact], *, request_size_for: Callable[[tuple[Fact, ...]], int]
) -> SelectionResult:
    """Apply the frozen request-budget decision and return original Fact objects.

    ``request_size_for`` lets the later generator layer measure its exact frozen
    request without making this domain module depend on prompts or provider
    schemas. The selection decision, four-byte token estimate, byte budget, and
    post-selection guard are fixed to the final fresh-run values.
    """

    source = tuple(facts)
    if len({fact.fact_id for fact in source}) != len(source):
        raise ValueError("Duplicate Fact IDs")

    full_request_bytes = request_size_for(source)
    selector_used = math.ceil(full_request_bytes / 4) > _MAX_ESTIMATED_INPUT_TOKENS
    selected_fact_bytes: int | None = None
    if selector_used:
        empty_request_bytes = request_size_for(())
        context_bytes = empty_request_bytes - 2
        selected, reason_values, selected_fact_bytes = _select_with_budget(
            source,
            max_input_bytes=_MAX_FACT_INPUT_BYTES,
            context_bytes=context_bytes,
        )
        reasons = {
            fact.fact_id: reason
            for fact, reason in zip(selected, reason_values, strict=True)
        }
        chosen = set(fact.fact_id for fact in selected)
        omitted_ids = tuple(fact.fact_id for fact in source if fact.fact_id not in chosen)
    else:
        selected = source
        reasons = {fact.fact_id: "full_input_fits" for fact in selected}
        omitted_ids = ()

    selected_request_bytes = request_size_for(selected)
    if math.ceil(selected_request_bytes / 4) > _MAX_SELECTED_ESTIMATED_TOKENS:
        raise ValueError("Selected request exceeds safe input estimate")

    return SelectionResult(
        facts=selected,
        selected_ids=tuple(fact.fact_id for fact in selected),
        omitted_ids=omitted_ids,
        selection_reasons=MappingProxyType(reasons),
        selector_used=selector_used,
        full_fact_count=len(source),
        selected_fact_count=len(selected),
        full_request_bytes=full_request_bytes,
        selected_request_bytes=selected_request_bytes,
        selected_fact_bytes=selected_fact_bytes,
    )
