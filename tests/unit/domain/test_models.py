from dataclasses import FrozenInstanceError, fields
import json

import pytest

from rca_ai.domain.enums import Decision, SupportLevel
from rca_ai.domain.models import (
    CandidateAnalysis,
    CandidateHypothesis,
    CandidateResult,
    CanonicalIncidentEvidence,
    CanonicalObservation,
    Fact,
    FactEntity,
    EvidenceEntity,
    EvidenceSource,
    HistoricalContext,
    Hypothesis,
    IncidentBasis,
    IncidentInput,
    KnowledgeItem,
    RCAResult,
    RelationAssessment,
    ValidationResult,
    to_dict,
)


def test_validator_enums_keep_the_frozen_json_values():
    assert [item.value for item in Decision] == ["KEEP", "KEEP_QUALIFIED", "REJECT"]
    assert [item.value for item in SupportLevel] == [
        "STRONG",
        "PLAUSIBLE",
        "WEAK",
        "CONTRADICTED",
    ]


def test_fact_preserves_nested_source_value_and_has_no_inference_fields():
    exact_value = {"available": 1, "desired": 1, "ready": 1, "updated": 1}
    fact = Fact(
        fact_id="F4",
        entity=FactEntity(type="workload", id="telemetry-docs"),
        field="replicas",
        value=exact_value,
        source_ref="kubernetes:001",
        source_path="/fields/replicas",
    )

    assert to_dict(fact) == {
        "fact_id": "F4",
        "entity": {"type": "workload", "id": "telemetry-docs"},
        "field": "replicas",
        "value": exact_value,
        "source_ref": "kubernetes:001",
        "source_path": "/fields/replicas",
    }
    assert [item.name for item in fields(Fact)] == [
        "fact_id",
        "entity",
        "field",
        "value",
        "source_ref",
        "source_path",
    ]
    with pytest.raises(FrozenInstanceError):
        fact.field = "generated_cause"


def test_incident_input_has_one_canonical_evidence_boundary():
    evidence = CanonicalIncidentEvidence(
        window={"baseline_start": 0, "incident_start": 1, "incident_end": 2},
        observations=(CanonicalObservation(
            observation_id="obs-1", signal="kubernetes",
            entity=EvidenceEntity("container", "docs"), field="waiting_reason",
            value="CreateContainerConfigError", attributes={"phase": "Pending"},
            source=EvidenceSource("src-1", "/observations/0/waiting_reason", ("pods.json:0",)),
        ),),
    )
    incident = IncidentInput("example-incident", evidence)

    assert to_dict(incident) == {"incident_id": "example-incident", "evidence": to_dict(evidence)}
    assert not hasattr(incident, "normalized_evidence")
    assert not hasattr(incident, "retrieval_input")


def test_history_and_knowledge_are_distinct_provenance_models():
    history = HistoricalContext(
        alias="H1",
        source_id="H021",
        record={"incident_id": "H021", "root_cause": "historical text"},
    )
    knowledge = KnowledgeItem(
        alias="K1",
        source_id="kubernetes.pod_phase.pending",
        record={
            "knowledge_key": "kubernetes.pod_phase.pending",
            "claim": "A Pending Pod has been accepted by the cluster.",
            "source": {"publisher": "Kubernetes"},
        },
    )

    assert type(history) is not type(knowledge)
    assert to_dict(history)["source_type"] == "HISTORY"
    assert to_dict(knowledge)["source_type"] == "DOMAIN_KNOWLEDGE"
    assert to_dict(knowledge)["record"]["knowledge_key"] == knowledge.source_id


def test_hypothesis_keeps_fact_history_and_knowledge_refs_separate():
    hypothesis = Hypothesis(
        id="HYP1",
        explanation="An observed dependency failure may explain the startup condition.",
        explains_fact_refs=("F8", "F9"),
        supporting_fact_refs=("F8",),
        history_refs=("H1",),
        knowledge_refs=("K2",),
        assumptions=("The dependency is required.",),
        unresolved=("Check the configuration reference.",),
    )

    payload = to_dict(hypothesis)
    assert payload["explains_fact_refs"] == ["F8", "F9"]
    assert payload["supporting_fact_refs"] == ["F8"]
    assert payload["history_refs"] == ["H1"]
    assert payload["knowledge_refs"] == ["K2"]
    assert "source_refs" not in payload


def test_validation_result_uses_compact_basis_and_independent_dimensions():
    result = ValidationResult(
        hypothesis_id="HYP1",
        decision=Decision.KEEP_QUALIFIED,
        support_level=SupportLevel.PLAUSIBLE,
        incident_basis=IncidentBasis(evidence=("F6", "F8")),
        hard_violations=(),
        qualifications=(),
        relation_assessment=RelationAssessment(
            relation="F8 may explain the observed startup condition.",
            support_level=SupportLevel.WEAK,
            fact_refs=("F8",),
            reason="The explanatory relation remains uncertain.",
        ),
        unresolved=("Inspect the referenced configuration.",),
    )

    payload = to_dict(result)
    assert payload["decision"] == "KEEP_QUALIFIED"
    assert payload["support_level"] == "PLAUSIBLE"
    assert payload["incident_basis"] == {"evidence": ["F6", "F8"]}
    assert payload["relation_assessment"]["support_level"] == "WEAK"


def test_final_result_accepts_abstention_without_synthetic_diagnosis():
    result = RCAResult(incident_id="ad-high-cpu-01", candidate_results=())

    assert to_dict(result) == {
        "incident_id": "ad-high-cpu-01",
        "candidate_results": [],
    }


def test_final_result_serializes_to_json_with_exact_candidate_shape():
    result = RCAResult(
        incident_id="missing-secret-01",
        candidate_results=(
            CandidateResult(
                incident_id="missing-secret-01",
                analysis=CandidateAnalysis(
                    decision=Decision.KEEP_QUALIFIED,
                    support_level=SupportLevel.STRONG,
                ),
                hypothesis=CandidateHypothesis(
                    id="HYP1",
                    explanation="A reported configuration lookup failure may explain startup waiting.",
                    assumptions=("The referenced configuration is required.",),
                    unresolved=("Verify the reference in the workload specification.",),
                ),
                evidence_refs=("F6", "F8"),
                history_refs=("H1",),
                knowledge_refs=("K2",),
                qualifications=(),
                validation_unresolved=("Verify the configured reference.",),
            ),
        ),
    )

    payload = to_dict(result)
    assert json.loads(json.dumps(payload)) == {
        "incident_id": "missing-secret-01",
        "candidate_results": [
            {
                "incident_id": "missing-secret-01",
                "analysis": {
                    "decision": "KEEP_QUALIFIED",
                    "support_level": "STRONG",
                },
                "hypothesis": {
                    "id": "HYP1",
                    "explanation": "A reported configuration lookup failure may explain startup waiting.",
                    "assumptions": ["The referenced configuration is required."],
                    "unresolved": ["Verify the reference in the workload specification."],
                },
                "evidence_refs": ["F6", "F8"],
                "history_refs": ["H1"],
                "knowledge_refs": ["K2"],
                "qualifications": [],
                "validation_unresolved": ["Verify the configured reference."],
            }
        ],
    }
