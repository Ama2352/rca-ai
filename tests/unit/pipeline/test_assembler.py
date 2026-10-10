from dataclasses import replace
import json
from pathlib import Path

import pytest

from rca_ai.domain.enums import Decision, SupportLevel
from rca_ai.domain.models import (
    CandidateHypothesis,
    Fact,
    FactEntity,
    HardViolation,
    HistoricalContext,
    Hypothesis,
    IncidentBasis,
    KnowledgeItem,
    Qualification,
    RelationAssessment,
    ValidationResult,
    to_dict,
)
from rca_ai.pipeline.assembler import assemble_result, resolve_sources
from rca_ai.reasoning.generator import validate_generation
from rca_ai.reasoning.validator import validate_validator_output
from rca_ai.retrieval.history import retrieve_history
from rca_ai.retrieval.knowledge import retrieve_knowledge


ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "fixtures"
CASES = (
    ("missing-secret-01", "channel-incident-01.json"),
    ("application-failure-01", "channel-incident-02.json"),
    ("ad-high-cpu-01", "channel-incident-01.json"),
)


def _fresh_case(incident_id, query_fixture):
    fact_rows = json.loads(
        (FIXTURES / "facts" / "expected" / "fact_views" / f"{incident_id}.json")
        .read_text(encoding="utf-8")
    )["facts"]
    facts = tuple(Fact(
        row["fact_id"], FactEntity(**row["entity"]), row["field"], row["value"],
        row["source_ref"], row["source_path"],
    ) for row in fact_rows)
    query_path = FIXTURES / "retrieval" / "inputs" / query_fixture
    retrieval_input = (
        query_path.read_text(encoding="utf-8").rstrip("\n")
        if query_path.suffix == ".txt"
        else json.loads(query_path.read_text(encoding="utf-8"))
    )
    history = retrieve_history(retrieval_input)
    knowledge = retrieve_knowledge(retrieval_input)
    fixture_root = FIXTURES / "reasoning" / "validator"
    generation = json.loads(
        (fixture_root / "inputs" / f"{incident_id}.generation.json").read_text(encoding="utf-8")
    )
    hypotheses = validate_generation(generation, facts, history.items, knowledge.items)
    validations = tuple(
        validate_validator_output(
            json.loads(
                (fixture_root / "expected" / incident_id / f"{hypothesis.id}.response.json")
                .read_text(encoding="utf-8")
            ),
            hypothesis,
            facts,
        )
        for hypothesis in hypotheses
    )
    return facts, history, knowledge, hypotheses, validations


def test_final_results_match_all_frozen_scenarios_and_reassemble_exactly():
    for incident_id, query_fixture in CASES:
        facts, history, knowledge, hypotheses, validations = _fresh_case(incident_id, query_fixture)
        first = assemble_result(incident_id, hypotheses, validations, facts, history, knowledge)
        second = assemble_result(incident_id, hypotheses, validations, facts, history, knowledge)
        expected = json.loads(
            (FIXTURES / "pipeline" / "assembler" / f"{incident_id}.final_result.json")
            .read_text(encoding="utf-8")
        )
        expected_sources = json.loads(
            (FIXTURES / "pipeline" / "assembler" / f"{incident_id}.resolved_sources.json")
            .read_text(encoding="utf-8")
        )

        assert to_dict(first) == expected
        assert to_dict(second) == expected
        resolved = [resolve_sources(candidate, facts, history, knowledge) for candidate in first.candidate_results]
        if incident_id != "ad-high-cpu-01":
            assert resolved == expected_sources
        else:
            assert len(resolved) == len(first.candidate_results)
            assert all(isinstance(row["evidence"], list) for row in resolved)


def _small_objects(decision=Decision.KEEP_QUALIFIED):
    facts = (Fact("F1", FactEntity("service", "svc"), "state", "failed", "src", "/state"),)
    history = (HistoricalContext("H1", "old-incident", {"incident_id": "old-incident", "root_cause": "historic"}),)
    knowledge = (KnowledgeItem("K1", "k-sem", {"knowledge_key": "k-sem", "claim": "general semantics"}),)
    hypothesis = Hypothesis(
        "HYP1", "A may explain B.", ("F1",), ("F1",), ("H1",), ("K1",),
        ("assumption exact",), ("hypothesis question",),
    )
    validation = ValidationResult(
        hypothesis_id="HYP1",
        decision=decision,
        support_level=SupportLevel.PLAUSIBLE,
        incident_basis=IncidentBasis(("F1",)),
        hard_violations=(),
        qualifications=(Qualification("claim exact", "issue exact", ("F1",), "observed form exact"),),
        relation_assessment=RelationAssessment("relation exact", SupportLevel.PLAUSIBLE, ("F1",), "reason exact"),
        unresolved=("validator question exact",),
    )
    return facts, history, knowledge, hypothesis, validation


def test_keep_and_keep_qualified_are_retained_reject_is_omitted_and_order_is_input_order():
    facts, history, knowledge, first_hypothesis, first_validation = _small_objects()
    rejected_hypothesis = replace(first_hypothesis, id="HYP2")
    rejected_validation = replace(first_validation, hypothesis_id="HYP2", decision=Decision.REJECT)
    kept_hypothesis = replace(first_hypothesis, id="HYP3")
    kept_validation = replace(first_validation, hypothesis_id="HYP3", decision=Decision.KEEP)

    result = assemble_result(
        "incident-x",
        (first_hypothesis, rejected_hypothesis, kept_hypothesis),
        (rejected_validation, first_validation, kept_validation),
        facts,
        history,
        knowledge,
    )

    assert [row.hypothesis.id for row in result.candidate_results] == ["HYP1", "HYP3"]
    assert [row.analysis.decision for row in result.candidate_results] == [
        Decision.KEEP_QUALIFIED, Decision.KEEP
    ]


def test_zero_retained_candidates_is_valid_empty_rca_result():
    facts, history, knowledge, hypothesis, validation = _small_objects(Decision.REJECT)
    result = assemble_result("incident-x", (hypothesis,), (validation,), facts, history, knowledge)
    assert to_dict(result) == {"incident_id": "incident-x", "candidate_results": []}


def test_assembler_preserves_all_semantic_text_and_provenance_sections():
    facts, history, knowledge, hypothesis, validation = _small_objects()
    result = assemble_result("incident-x", (hypothesis,), (validation,), facts, history, knowledge)
    candidate = result.candidate_results[0]
    resolved = resolve_sources(candidate, facts, history, knowledge)

    assert candidate.hypothesis == CandidateHypothesis(
        "HYP1", "A may explain B.", ("assumption exact",), ("hypothesis question",)
    )
    assert candidate.qualifications == validation.qualifications
    assert candidate.validation_unresolved == validation.unresolved
    assert candidate.evidence_refs == ("F1",)
    assert candidate.history_refs == ("H1",)
    assert candidate.knowledge_refs == ("K1",)
    assert resolved["evidence"] == [to_dict(facts[0])]
    assert resolved["history"] == [to_dict(history[0])]
    assert resolved["domain_knowledge"] == [to_dict(knowledge[0])]
    assert "historic" not in json.dumps(resolved["evidence"])
    assert "general semantics" not in json.dumps(resolved["evidence"])


@pytest.mark.parametrize(
    ("namespace", "bad_ref"),
    [("evidence", "F404"), ("evidence", "H1"), ("evidence", "K1"),
     ("history", "H404"), ("history", "F1"), ("knowledge", "K404"), ("knowledge", "F1")],
)
def test_unknown_or_cross_namespace_refs_fail_closed(namespace, bad_ref):
    facts, history, knowledge, hypothesis, validation = _small_objects()
    if namespace == "evidence":
        validation = replace(validation, incident_basis=IncidentBasis((bad_ref,)))
    elif namespace == "history":
        hypothesis = replace(hypothesis, history_refs=(bad_ref,))
    else:
        hypothesis = replace(hypothesis, knowledge_refs=(bad_ref,))
    with pytest.raises(ValueError):
        assemble_result("incident-x", (hypothesis,), (validation,), facts, history, knowledge)


def test_unknown_hypothesis_fact_refs_and_validator_refs_fail():
    facts, history, knowledge, hypothesis, validation = _small_objects()
    bad_cases = (
        (replace(hypothesis, explains_fact_refs=("F404",)), validation),
        (replace(hypothesis, supporting_fact_refs=("F404",)), validation),
        (hypothesis, replace(validation, relation_assessment=replace(
            validation.relation_assessment, fact_refs=("F404",)
        ))),
        (hypothesis, replace(validation, hard_violations=(
            HardViolation("claim", "type", ("F404",), "reason"),
        ))),
        (hypothesis, replace(validation, qualifications=(
            Qualification("claim", "issue", ("F404",), "observed"),
        ))),
    )
    for bad_hypothesis, bad_validation in bad_cases:
        with pytest.raises(ValueError):
            assemble_result("incident-x", (bad_hypothesis,), (bad_validation,),
                            facts, history, knowledge)


def test_validation_matching_rejects_mismatch_missing_duplicate_and_unknown_results():
    facts, history, knowledge, hypothesis, validation = _small_objects()
    with pytest.raises(ValueError, match="Missing or mismatched"):
        assemble_result("incident-x", (hypothesis,), (), facts, history, knowledge)
    with pytest.raises(ValueError, match="Duplicate validation"):
        assemble_result("incident-x", (hypothesis,), (validation, validation), facts, history, knowledge)
    with pytest.raises(ValueError, match="Unknown validation"):
        assemble_result("incident-x", (hypothesis,),
                        (replace(validation, hypothesis_id="HYP404"),), facts, history, knowledge)


def test_source_namespaces_must_not_overlap_by_store_identity():
    facts, history, knowledge, hypothesis, validation = _small_objects()
    colliding_fact = replace(facts[0], fact_id="H1")
    with pytest.raises(ValueError, match="overlap"):
        assemble_result("incident-x", (hypothesis,), (validation,), (colliding_fact,), history, knowledge)
