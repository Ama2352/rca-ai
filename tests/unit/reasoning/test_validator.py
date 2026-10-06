import hashlib
import json
from pathlib import Path

import pytest

from rca_ai.domain.enums import Decision, SupportLevel
from rca_ai.domain.models import (
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
from rca_ai.providers.groq import ProviderError, ProviderResult
from rca_ai.reasoning.prompts import VALIDATOR_SYSTEM_PROMPT
from rca_ai.reasoning.schemas import VALIDATOR_JSON_SCHEMA
from rca_ai.reasoning.validator import (
    HypothesisValidator,
    ValidatorValidationError,
    build_validator_request,
    validate_validator_output,
)


ROOT = Path(__file__).resolve().parents[3]
FIXTURES = ROOT / "tests" / "fixtures"
VALIDATOR_FIXTURES = FIXTURES / "reasoning" / "validator"
SCENARIOS = (
    ("missing-secret-01", "channel-incident-01.json"),
    ("application-failure-01", "channel-incident-02.json"),
    ("ad-high-cpu-01", "channel-incident-01.json"),
)


def _context(incident_id, retrieval_name):
    from rca_ai.domain.models import FactEntity
    from rca_ai.facts.selector import request_bytes, select_facts
    from rca_ai.reasoning.generator import build_generator_request, validate_generation
    from rca_ai.retrieval.history import retrieve_history
    from rca_ai.retrieval.knowledge import retrieve_knowledge

    fact_rows = json.loads(
        (FIXTURES / "facts" / "expected" / "fact_views" / f"{incident_id}.json")
        .read_text(encoding="utf-8")
    )["facts"]
    full_facts = tuple(Fact(
        row["fact_id"], FactEntity(**row["entity"]), row["field"], row["value"],
        row["source_ref"], row["source_path"],
    ) for row in fact_rows)
    query_path = FIXTURES / "retrieval" / "inputs" / retrieval_name
    query = (
        query_path.read_text(encoding="utf-8").rstrip("\n")
        if query_path.suffix == ".txt"
        else json.loads(query_path.read_text(encoding="utf-8"))
    )
    history = retrieve_history(query)
    knowledge = retrieve_knowledge(query)
    size_for = lambda facts: len(json.dumps(
        build_generator_request(facts, history, knowledge),
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8"))
    selection = select_facts(full_facts, request_size_for=size_for)
    generation = json.loads(
        (VALIDATOR_FIXTURES / "inputs" / f"{incident_id}.generation.json").read_text(encoding="utf-8")
    )
    hypotheses = validate_generation(generation, selection.facts, history.items, knowledge.items)
    return selection.facts, history, knowledge, hypotheses


def test_frozen_validator_prompt_and_effective_schema_hashes_match():
    assert hashlib.sha256(VALIDATOR_SYSTEM_PROMPT.encode("utf-8")).hexdigest() == (
        "1b61f29d658c079b27b18ca0d0ea3e59b96e3989f21eef0368d9a1d17c86e6b6"
    )
    assert hashlib.sha256(json.dumps(VALIDATOR_JSON_SCHEMA, sort_keys=True).encode("utf-8")).hexdigest() == (
        "3fc8c2fe12d2748fc934cfe3ae0bd50ca0db1a13891d71df7922d1e6daeebc06"
    )
    basis = VALIDATOR_JSON_SCHEMA["properties"]["incident_basis"]
    assert basis["type"] == "object"
    assert basis["properties"]["evidence"]["type"] == "array"
    assert "fact_ref" not in basis.get("properties", {})


def test_request_config_and_compact_basis_are_frozen():
    expected = json.loads(
        (VALIDATOR_FIXTURES / "expected" / "missing-secret-01" / "HYP1.request.json").read_text(encoding="utf-8")
    )
    assert list(expected) == [
        "model", "reasoning_effort", "include_reasoning", "temperature",
        "max_completion_tokens", "messages", "response_format",
    ]
    assert expected["model"] == "openai/gpt-oss-120b"
    assert expected["reasoning_effort"] == "medium"
    assert expected["include_reasoning"] is False
    assert expected["temperature"] == 0
    assert expected["max_completion_tokens"] == 4096
    assert expected["response_format"]["type"] == "json_schema"
    assert expected["response_format"]["json_schema"]["strict"] is True
    assert expected["response_format"]["json_schema"]["schema"] == VALIDATOR_JSON_SCHEMA


@pytest.mark.parametrize(("incident_id", "retrieval_name"), SCENARIOS)
def test_every_fresh_validator_request_matches_frozen_candidate_request(incident_id, retrieval_name):
    facts, history, knowledge, hypotheses = _context(incident_id, retrieval_name)
    for hypothesis in hypotheses:
        actual = build_validator_request(hypothesis, facts, history, knowledge)
        expected = json.loads(
            (VALIDATOR_FIXTURES / "expected" / incident_id / f"{hypothesis.id}.request.json")
            .read_text(encoding="utf-8")
        )
        payload = json.loads(actual["messages"][1]["content"])
        if incident_id != "ad-high-cpu-01":
            assert actual == expected
        else:
            # The frozen ad request captured the removed plain-query path.
            # Its saved response remains useful for output-contract parsing only.
            assert len(payload["current_facts"]) == len(facts)
            assert all(row["source_type"] == "HISTORY" for row in payload["history"])
            assert all(row["source_type"] == "DOMAIN_KNOWLEDGE" for row in payload["domain_knowledge"])
        assert len([payload["candidate_hypothesis"]]) == 1
        assert payload["candidate_hypothesis"]["explanation"] == hypothesis.explanation
        assert [row["fact_id"] for row in payload["current_facts"]] == [fact.fact_id for fact in facts]


@pytest.mark.parametrize(("incident_id", "retrieval_name"), SCENARIOS)
def test_saved_frozen_validator_responses_map_to_domain_without_rewriting(incident_id, retrieval_name):
    facts, _, _, hypotheses = _context(incident_id, retrieval_name)
    for hypothesis in hypotheses:
        output = json.loads(
            (VALIDATOR_FIXTURES / "expected" / incident_id / f"{hypothesis.id}.response.json")
            .read_text(encoding="utf-8")
        )
        result = validate_validator_output(output, hypothesis, facts)
        assert to_dict(result) == output


class FakeProvider:
    def __init__(self, content=None, error=None):
        self.content = content
        self.error = error
        self.requests = []

    def complete(self, request):
        self.requests.append(request)
        if self.error:
            raise self.error
        return ProviderResult(
            content=self.content,
            raw_content=json.dumps(self.content),
            http_status=200,
            attempts=1,
            response_id="test-response",
            model_returned="openai/gpt-oss-120b",
            finish_reason="stop",
            usage={"prompt_tokens": 2, "completion_tokens": 2},
            latency_seconds=0,
            rate_limit_headers={},
            attempt_log=(),
        )


def _fixture_context():
    from rca_ai.retrieval.history import HistoryRetrievalResult
    from rca_ai.retrieval.knowledge import KnowledgeRetrievalResult

    facts = (Fact("F1", FactEntity("service", "svc"), "state", "error", "src", "/state"),)
    history = HistoryRetrievalResult(
        query="q", strategy="channel_bm25_rrf",
        items=(HistoricalContext("H1", "history-1", {"incident_id": "history-1"}),), metadata={},
    )
    knowledge = KnowledgeRetrievalResult(
        query="q", items=(KnowledgeItem("K1", "knowledge-1", {"knowledge_key": "knowledge-1", "claim": "general"}),),
        ranking=(("knowledge-1", 0.5),),
    )
    hypothesis = Hypothesis(
        "HYP1", "A may explain B.", ("F1",), ("F1",), ("H1",), ("K1",), (), ()
    )
    return facts, history, knowledge, hypothesis


def _valid_result(decision="KEEP_QUALIFIED", support="PLAUSIBLE"):
    return {
        "hypothesis_id": "HYP1",
        "decision": decision,
        "support_level": support,
        "incident_basis": {"evidence": ["F1"]},
        "hard_violations": [],
        "qualifications": [],
        "relation_assessment": {
            "relation": "A may explain B.",
            "support_level": support,
            "fact_refs": ["F1"],
            "reason": "The relation remains a proposal.",
        },
        "unresolved": ["Collect distinguishing evidence."],
    }


@pytest.mark.parametrize(
    ("decision", "support"),
    [
        ("KEEP", "STRONG"),
        ("KEEP_QUALIFIED", "STRONG"),
        ("KEEP_QUALIFIED", "PLAUSIBLE"),
        ("KEEP_QUALIFIED", "WEAK"),
        ("REJECT", "CONTRADICTED"),
    ],
)
def test_valid_decision_and_support_combinations_remain_independent(decision, support):
    facts, history, knowledge, hypothesis = _fixture_context()
    output = _valid_result(decision, support)
    execution = HypothesisValidator(FakeProvider(output)).validate(
        hypothesis, facts, history, knowledge
    )
    assert execution.result.decision.value == decision
    assert execution.result.support_level.value == support
    assert execution.result.relation_assessment.support_level.value == support


def test_validation_model_preserves_compact_refs_and_never_rewrites_hypothesis():
    facts, history, knowledge, hypothesis = _fixture_context()
    output = _valid_result("KEEP_QUALIFIED", "PLAUSIBLE")
    execution = HypothesisValidator(FakeProvider(output)).validate(
        hypothesis, facts, history, knowledge
    )
    assert isinstance(execution.result, ValidationResult)
    assert execution.result.incident_basis == IncidentBasis(("F1",))
    assert to_dict(execution.result) == output
    assert json.loads(execution.request["messages"][1]["content"])["candidate_hypothesis"]["explanation"] == (
        hypothesis.explanation
    )
    assert hypothesis.explanation == "A may explain B."


@pytest.mark.parametrize(
    ("path", "value"),
    [
        (("incident_basis", "evidence"), ["F404"]),
        (("qualifications",), [{"claim": "x", "issue": "x", "fact_refs": ["F404"], "observed_form": "x"}]),
        (("hard_violations",), [{"claim": "x", "type": "x", "fact_refs": ["F404"], "reason": "x"}]),
        (("relation_assessment", "fact_refs"), ["F404"]),
    ],
)
def test_unknown_fact_references_fail(path, value):
    facts, history, knowledge, hypothesis = _fixture_context()
    output = _valid_result()
    target = output
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value
    with pytest.raises(ValidatorValidationError):
        HypothesisValidator(FakeProvider(output)).validate(hypothesis, facts, history, knowledge)


def test_identity_schema_and_old_basis_shape_fail():
    facts, history, knowledge, hypothesis = _fixture_context()
    mismatched = _valid_result()
    mismatched["hypothesis_id"] = "HYP2"
    with pytest.raises(ValidatorValidationError, match="identity"):
        HypothesisValidator(FakeProvider(mismatched)).validate(hypothesis, facts, history, knowledge)
    for key, value in (("decision", "UNKNOWN"), ("support_level", "MAYBE")):
        invalid = _valid_result()
        invalid[key] = value
        with pytest.raises(ValidatorValidationError):
            HypothesisValidator(FakeProvider(invalid)).validate(hypothesis, facts, history, knowledge)
    old_basis = _valid_result()
    old_basis["incident_basis"] = [{"fact_ref": "F1", "role": "evidence"}]
    with pytest.raises(ValidatorValidationError):
        HypothesisValidator(FakeProvider(old_basis)).validate(hypothesis, facts, history, knowledge)
    extra = _valid_result()
    extra["extra"] = "not allowed"
    with pytest.raises(ValidatorValidationError):
        HypothesisValidator(FakeProvider(extra)).validate(hypothesis, facts, history, knowledge)


def test_provider_error_propagates_and_weak_plausible_is_not_rejected_by_wrapper():
    facts, history, knowledge, hypothesis = _fixture_context()
    provider_error = ProviderError("provider failed", attempts=3)
    with pytest.raises(ProviderError) as raised:
        HypothesisValidator(FakeProvider(error=provider_error)).validate(
            hypothesis, facts, history, knowledge
        )
    assert raised.value is provider_error
    output = _valid_result("KEEP_QUALIFIED", "WEAK")
    result = HypothesisValidator(FakeProvider(output)).validate(hypothesis, facts, history, knowledge)
    assert result.result.decision is Decision.KEEP_QUALIFIED
    assert result.result.relation_assessment.support_level is SupportLevel.WEAK
