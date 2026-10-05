from dataclasses import replace
import json
from pathlib import Path

import pytest

from rca_ai.domain.models import Fact, FactEntity, IncidentInput, to_dict
from rca_ai.facts.builder import build_fact_view, verify_fact_view


ROOT = Path(__file__).resolve().parents[3]
FIXTURES = ROOT / "tests" / "fixtures" / "facts"
CASES = (
    ("missing-secret-01", 21),
    ("application-failure-01", 52),
    ("ad-high-cpu-01", 14),
)


def _load_case(incident_id):
    normalized = json.loads(
        (FIXTURES / "inputs" / f"{incident_id}.normalized.json").read_text(encoding="utf-8")
    )
    expected = json.loads(
        (FIXTURES / "expected" / "fact_views" / f"{incident_id}.json").read_text(encoding="utf-8")
    )["facts"]
    return IncidentInput(incident_id=incident_id, normalized_evidence=normalized), expected


def _canonical_json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


@pytest.mark.parametrize(("incident_id", "expected_count"), CASES)
def test_builder_matches_frozen_fact_view_exactly(incident_id, expected_count):
    incident, expected = _load_case(incident_id)

    actual = tuple(to_dict(fact) for fact in build_fact_view(incident))

    assert len(actual) == expected_count
    assert _canonical_json(actual) == _canonical_json(expected)
    assert verify_fact_view(tuple(build_fact_view(incident)), incident) is True


@pytest.mark.parametrize(("incident_id", "expected_count"), CASES)
def test_fact_ids_are_stable_and_repeatable(incident_id, expected_count):
    incident, _ = _load_case(incident_id)

    first = build_fact_view(incident)
    second = build_fact_view(incident)

    assert tuple(fact.fact_id for fact in first) == tuple(
        f"F{number}" for number in range(1, expected_count + 1)
    )
    assert tuple(to_dict(fact) for fact in first) == tuple(to_dict(fact) for fact in second)


@pytest.mark.parametrize(("incident_id", "_expected_count"), CASES)
def test_builder_does_not_mutate_normalized_input(incident_id, _expected_count):
    incident, _ = _load_case(incident_id)
    before = _canonical_json(incident.normalized_evidence)

    build_fact_view(incident)

    assert _canonical_json(incident.normalized_evidence) == before


def test_fact_output_contains_only_the_frozen_observation_fields():
    incident, _ = _load_case("missing-secret-01")

    fact_rows = [to_dict(fact) for fact in build_fact_view(incident)]

    assert all(
        set(row) == {"fact_id", "source_ref", "entity", "field", "value", "source_path"}
        for row in fact_rows
    )
    assert isinstance(build_fact_view(incident), tuple)


def test_unknown_normalized_shape_is_not_silently_projected():
    incident = IncidentInput("unknown", {"unrecognized": {"state": "surprising"}})

    with pytest.raises(ValueError, match="Unsupported normalized evidence shape"):
        build_fact_view(incident)


@pytest.mark.parametrize(
    "mutate",
    (
        lambda fact: replace(fact, value="changed"),
        lambda fact: replace(fact, source_ref="wrong:source"),
        lambda fact: replace(fact, source_path="/wrong/path"),
        lambda fact: replace(fact, entity=FactEntity(type="service", id="wrong")),
        lambda fact: replace(fact, field="wrong_field"),
    ),
    ids=("value", "source-ref", "source-path", "entity", "field"),
)
def test_integrity_verifier_rejects_stale_or_mutated_projection(mutate):
    incident, _ = _load_case("missing-secret-01")
    facts = build_fact_view(incident)
    tampered = (mutate(facts[0]),) + facts[1:]

    with pytest.raises(ValueError, match="Fact projection differs"):
        verify_fact_view(tampered, incident)


def test_integrity_verifier_rejects_reordered_projection():
    incident, _ = _load_case("application-failure-01")
    facts = build_fact_view(incident)

    with pytest.raises(ValueError, match="Fact projection differs"):
        verify_fact_view((facts[1], facts[0], *facts[2:]), incident)
