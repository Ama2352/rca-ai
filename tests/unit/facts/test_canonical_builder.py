from copy import deepcopy
from pathlib import Path

import pytest

from rca_ai.domain.models import (
    CanonicalIncidentEvidence,
    CanonicalObservation,
    EvidenceEntity,
    EvidenceSource,
    IncidentInput,
    to_dict,
)
from rca_ai.facts.builder import build_fact_view, verify_fact_view


def _evidence():
    return CanonicalIncidentEvidence(
        window={"baseline_start": 1, "incident_start": 2, "incident_end": 3},
        observations=(
            CanonicalObservation(
                observation_id="obs-001", signal="metric", entity=EvidenceEntity("service", "checkout"),
                field="metric.counter_rate", value={"metric": "requests_total", "incident_value": 12},
                attributes={"metric_kind": "counter"},
                source=EvidenceSource("src-001", "/metrics/0", ("metrics.json:rows[4]",)),
            ),
            CanonicalObservation(
                observation_id="obs-002", signal="kubernetes", entity=EvidenceEntity("container", "checkout"),
                field="waiting_reason", value="ConfigError", attributes={"phase": "Pending"},
                source=EvidenceSource("src-002", "/kubernetes/0/waiting_reason", ("pods.json:items[0]",)),
            ),
        ),
    )


def test_projection_is_one_generic_fact_per_observation_with_exact_provenance():
    incident = IncidentInput("demo", _evidence())
    facts = build_fact_view(incident)

    assert [to_dict(item) for item in facts] == [
        {"fact_id": "F1", "entity": {"type": "service", "id": "checkout"},
         "field": "metric.counter_rate", "value": {"metric": "requests_total", "incident_value": 12},
         "source_ref": "src-001", "source_path": "/metrics/0"},
        {"fact_id": "F2", "entity": {"type": "container", "id": "checkout"},
         "field": "waiting_reason", "value": "ConfigError", "source_ref": "src-002",
         "source_path": "/kubernetes/0/waiting_reason"},
    ]
    assert verify_fact_view(facts, incident)


def test_projection_is_deterministic_and_does_not_mutate_canonical_evidence():
    evidence = _evidence()
    before = deepcopy(to_dict(evidence))
    incident = IncidentInput("demo", evidence)

    first = tuple(to_dict(item) for item in build_fact_view(incident))
    second = tuple(to_dict(item) for item in build_fact_view(incident))

    assert first == second
    assert to_dict(evidence) == before


def test_unknown_signal_fails_clearly():
    observation = CanonicalObservation(
        observation_id="obs-x", signal="unknown", entity=EvidenceEntity("service", "checkout"),
        field="x", value=1, attributes={}, source=EvidenceSource("src-x", "/x"),
    )
    incident = IncidentInput("demo", CanonicalIncidentEvidence({}, (observation,)))
    with pytest.raises(ValueError, match="Unsupported canonical signal"):
        build_fact_view(incident)


def test_fact_projection_has_no_scenario_name_routing():
    source = Path(__file__).resolve().parents[3] / "src" / "rca_ai" / "facts" / "builder.py"
    text = source.read_text(encoding="utf-8")
    assert all(name not in text for name in ("missing-secret-01", "application-failure-01", "ad-high-cpu-01"))
