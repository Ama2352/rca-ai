"""Deterministic, one-observation-to-one-Fact projection.

Canonical ownership and source paths are assigned upstream while telemetry
structure is known. The RCA layer copies those contracts verbatim; it does not
reinterpret modality fields or add diagnostic meaning.
"""

from copy import deepcopy

from rca_ai.domain.models import Fact, FactEntity, IncidentInput


_SUPPORTED_SIGNALS = frozenset({"metric", "log", "trace", "kubernetes"})


def _project(incident: IncidentInput) -> tuple[Fact, ...]:
    observations = incident.evidence.observations
    ids = [item.observation_id for item in observations]
    if len(ids) != len(set(ids)):
        raise ValueError("Canonical observation IDs must be unique")
    facts = []
    for index, observation in enumerate(observations, 1):
        if observation.signal not in _SUPPORTED_SIGNALS:
            raise ValueError(f"Unsupported canonical signal: {observation.signal}")
        if not observation.observation_id or not observation.source.source_ref or not observation.source.source_path:
            raise ValueError("Canonical observation requires identity and source provenance")
        if not observation.entity.type or not observation.entity.id:
            raise ValueError("Canonical observation requires an explicit entity owner")
        facts.append(Fact(
            fact_id=f"F{index}",
            entity=FactEntity(observation.entity.type, observation.entity.id),
            field=observation.field,
            value=deepcopy(observation.value),
            source_ref=observation.source.source_ref,
            source_path=observation.source.source_path,
        ))
    return tuple(facts)


def build_fact_view(incident: IncidentInput) -> tuple[Fact, ...]:
    """Build one immutable Fact from each canonical observation in stable order."""
    return _project(incident)


def verify_fact_view(facts: tuple[Fact, ...], incident: IncidentInput) -> bool:
    """Independently rebuild the projection and reject stale/reordered Facts."""
    try:
        return tuple(facts) == _project(incident)
    except (KeyError, TypeError, ValueError):
        return False
