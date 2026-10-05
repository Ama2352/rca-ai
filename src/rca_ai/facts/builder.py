"""Deterministic projections from normalized incident input into immutable Facts.

This module is the provenance boundary: normalized observations become `F`
records here. The projection is structural, preserving source ownership,
field, value, path, and order; causal inference and semantic rewriting are
forbidden because they would turn derived statements into apparent Evidence.
"""

from copy import deepcopy
import json
from typing import Any, Mapping

from rca_ai.domain.models import Fact, FactEntity, IncidentInput, to_dict


def _new_fact(number: int, source_ref: str, entity_type: str, entity_id: str,
              field: str, value: Any, source_path: str) -> Fact:
    return Fact(
        fact_id=f"F{number}",
        source_ref=source_ref,
        entity=FactEntity(type=entity_type, id=entity_id),
        field=field,
        value=deepcopy(value),
        source_path=source_path,
    )


def _is_container_event_shape(normalized: Mapping[str, Any]) -> bool:
    return all(key in normalized for key in ("container_state", "failed_event", "metric"))


def _is_composite_shape(normalized: Mapping[str, Any]) -> bool:
    records = normalized.get("facts")
    return isinstance(records, list) and all(
        isinstance(record, Mapping) and "fields" in record and "evidence_id" in record
        for record in records
    )


def _is_grouped_shape(normalized: Mapping[str, Any]) -> bool:
    groups = normalized.get("groups")
    return isinstance(groups, list) and all(
        isinstance(group, Mapping) and isinstance(group.get("observations"), list)
        for group in groups
    )


def _project_container_event(normalized: Mapping[str, Any]) -> tuple[Fact, ...]:
    facts: list[Fact] = []
    for record_name in ("container_state", "failed_event"):
        record = normalized[record_name]
        source_ref = record["original_ref"]
        for field, value in record["fields"].items():
            if field == "phase":
                entity_type, identity_path = "pod", "/raw_pod_name"
            elif field in {
                "state", "waiting_reason", "waiting_message", "restart_count", "ready", "container"
            } and record["fields"]["container"]:
                # These normalized fields describe the container and must stay
                # attached to it rather than moving to its Pod/workload parent.
                entity_type, identity_path = "container", "/fields/container"
            elif field.startswith("event_"):
                entity_type, identity_path = "event_record", "/original_ref"
            else:
                entity_type, identity_path = "workload", "/fields/workload"
            identity: Any = record
            for part in identity_path.split("/")[1:]:
                identity = identity[part]
            facts.append(_new_fact(
                len(facts) + 1,
                source_ref,
                entity_type,
                identity,
                field,
                value,
                "/fields/" + field,
            ))

    metric = normalized["metric"]
    fields_value = metric["fields"]
    facts.append(_new_fact(
        len(facts) + 1,
        metric["evidence_id"],
        "service",
        fields_value["service"],
        "fields",
        fields_value,
        "/fields",
    ))
    return tuple(facts)


def _project_composite(normalized: Mapping[str, Any]) -> tuple[Fact, ...]:
    facts = []
    for index, record in enumerate(normalized["facts"], 1):
        fields_value = record["fields"]
        if "service" in fields_value:
            entity_type, entity_id = "service", fields_value["service"]
        else:
            entity_type, entity_id = "observed_edge", record["evidence_id"]
        facts.append(_new_fact(
            index,
            record["evidence_id"],
            entity_type,
            entity_id,
            "fields",
            fields_value,
            f"/facts/{index - 1}/fields",
        ))
    return tuple(facts)


def _project_grouped(normalized: Mapping[str, Any]) -> tuple[Fact, ...]:
    facts = []
    for group in normalized["groups"]:
        for observation in group["observations"]:
            value = observation["record"]["fact"]
            entity_key = "resource" if value.get("resource") else "service"
            facts.append(_new_fact(
                len(facts) + 1,
                observation["source_id"],
                entity_key,
                value[entity_key],
                "fact",
                value,
                "/fact",
            ))
    return tuple(facts)


def _project(normalized: Mapping[str, Any]) -> tuple[Fact, ...]:
    """Route only by the normalized structure, never by incident identity."""

    projections = (
        (_is_container_event_shape, _project_container_event),
        (_is_composite_shape, _project_composite),
        (_is_grouped_shape, _project_grouped),
    )
    matches = [project for matches_shape, project in projections if matches_shape(normalized)]
    if len(matches) != 1:
        raise ValueError("Unsupported normalized evidence shape")
    return matches[0](normalized)


def build_fact_view(incident: IncidentInput) -> tuple[Fact, ...]:
    """Build the stable ordered Fact sequence from a supported normalized input.

    The input payload is selected by structural contract only. Values are
    copied without interpretation so later mutation of the input mapping does
    not mutate the built Facts; every Fact receives its sequential F identifier
    in the frozen projection order.
    """

    return _project(incident.normalized_evidence)


def _canonical_fact(fact: Fact) -> str:
    return json.dumps(to_dict(fact), ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def verify_fact_view(facts: tuple[Fact, ...], incident: IncidentInput) -> bool:
    """Check a Fact sequence against a fresh exact structural projection.

    This catches stale/reordered IDs, ownership, path, source, field, and value
    drift. It is an integrity check against the normalized contract, not a
    semantic validator.
    """

    expected = _project(incident.normalized_evidence)
    if len(facts) != len(expected):
        raise ValueError("Fact projection differs from normalized evidence")
    if any(_canonical_fact(actual) != _canonical_fact(want) for actual, want in zip(facts, expected)):
        raise ValueError("Fact projection differs from normalized evidence")
    return True
