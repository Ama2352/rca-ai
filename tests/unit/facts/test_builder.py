from dataclasses import replace

from rca_ai.domain.models import FactEntity, IncidentInput
from rca_ai.facts.builder import build_fact_view, verify_fact_view
from tests.unit.facts.test_canonical_builder import _evidence


def test_verifier_rejects_changed_value_source_owner_and_order():
    incident = IncidentInput("contract-test", _evidence())
    facts = build_fact_view(incident)

    changed_value = (replace(facts[0], value={"different": True}), *facts[1:])
    changed_source = (replace(facts[0], source_ref="wrong"), *facts[1:])
    changed_owner = (replace(facts[0], entity=FactEntity("service", "other")), *facts[1:])

    assert not verify_fact_view(changed_value, incident)
    assert not verify_fact_view(changed_source, incident)
    assert not verify_fact_view(changed_owner, incident)
    assert not verify_fact_view((facts[1], facts[0]), incident)


def test_every_fact_is_traceable_to_one_canonical_observation():
    incident = IncidentInput("contract-test", _evidence())
    observations = {row.source.source_ref: row for row in incident.evidence.observations}

    for fact in build_fact_view(incident):
        observation = observations[fact.source_ref]
        assert fact.entity == FactEntity(observation.entity.type, observation.entity.id)
        assert fact.field == observation.field
        assert fact.value == observation.value
        assert fact.source_path == observation.source.source_path
