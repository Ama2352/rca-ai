import hashlib
import json
from pathlib import Path

import pytest

from rca_ai.domain.models import Fact, FactEntity, Hypothesis
from rca_ai.facts.selector import request_bytes, select_facts
from rca_ai.providers.groq import ProviderError, ProviderResult
from rca_ai.reasoning.generator import (
    GenerationValidationError,
    HypothesisGenerator,
    build_generator_request,
)
from rca_ai.reasoning.prompts import GENERATOR_SYSTEM_PROMPT
from rca_ai.reasoning.schemas import GENERATOR_JSON_SCHEMA
from rca_ai.retrieval.history import retrieve_history
from rca_ai.retrieval.knowledge import retrieve_knowledge


ROOT = Path(__file__).resolve().parents[3]
FIXTURES = ROOT / "tests" / "fixtures"
GENERATOR_FIXTURES = FIXTURES / "reasoning" / "generator"
SCENARIOS = (
    ("missing-secret-01", "channel-incident-01.json"),
    ("application-failure-01", "channel-incident-02.json"),
    ("ad-high-cpu-01", "channel-incident-01.json"),
)


def _case(incident_id, retrieval_name):
    rows = json.loads(
        (FIXTURES / "facts" / "expected" / "fact_views" / f"{incident_id}.json")
        .read_text(encoding="utf-8")
    )["facts"]
    facts = tuple(Fact(
        row["fact_id"], FactEntity(**row["entity"]), row["field"], row["value"],
        row["source_ref"], row["source_path"],
    ) for row in rows)
    retrieval_path = FIXTURES / "retrieval" / "inputs" / retrieval_name
    retrieval_input = (
        retrieval_path.read_text(encoding="utf-8").rstrip("\n")
        if retrieval_path.suffix == ".txt"
        else json.loads(retrieval_path.read_text(encoding="utf-8"))
    )
    history = retrieve_history(retrieval_input)
    knowledge = retrieve_knowledge(retrieval_input)
    return facts, history, knowledge


def _request_for_case(incident_id, retrieval_name):
    facts, history, knowledge = _case(incident_id, retrieval_name)
    size_for = lambda selected: request_bytes(
        build_generator_request(selected, history, knowledge)
    )
    selection = select_facts(facts, request_size_for=size_for)
    return selection, build_generator_request(selection.facts, history, knowledge)


def test_frozen_generator_prompt_and_schema_hashes_match():
    assert hashlib.sha256(GENERATOR_SYSTEM_PROMPT.encode("utf-8")).hexdigest() == (
        "2902e2200777ea4731cd0baaf9cff616e9ee637c0a1344202fbc9d32607c98de"
    )
    assert hashlib.sha256(json.dumps(GENERATOR_JSON_SCHEMA, sort_keys=True).encode("utf-8")).hexdigest() == (
        "26df3bd25892a50bdad1859b31d1a3fe1dd35fdf92f15fce9954d25abcc10119"
    )


def test_request_uses_frozen_model_and_strict_structured_output():
    request = json.loads((GENERATOR_FIXTURES / "template.json").read_text(encoding="utf-8"))
    assert request["model"] == "openai/gpt-oss-120b"
    assert request["reasoning_effort"] == "medium"
    assert request["include_reasoning"] is False
    assert request["temperature"] == 0
    assert request["max_completion_tokens"] == 4096
    assert request["response_format"]["type"] == "json_schema"
    assert request["response_format"]["json_schema"]["strict"] is True


@pytest.mark.parametrize(("incident_id", "retrieval_name"), SCENARIOS)
def test_fresh_fact_retrieval_selection_and_request_match_frozen_contract(
    incident_id, retrieval_name
):
    selection, actual = _request_for_case(incident_id, retrieval_name)
    expected = None if incident_id == "ad-high-cpu-01" else json.loads(
        (GENERATOR_FIXTURES / "expected" / f"{incident_id}.request.json").read_text(encoding="utf-8")
    )

    expected_counts = {
        "missing-secret-01": (21, 21),
        "application-failure-01": (52, 25),
        "ad-high-cpu-01": (14, 14),
    }
    assert (selection.full_fact_count, selection.selected_fact_count) == expected_counts[incident_id]
    supplied = json.loads(actual["messages"][1]["content"])
    assert [fact["fact_id"] for fact in supplied["current_facts"]] == list(selection.selected_ids)
    assert all(row["source_type"] == "HISTORY" for row in supplied["history"])
    assert all(row["source_type"] == "DOMAIN_KNOWLEDGE" for row in supplied["domain_knowledge"])
    if expected is not None:
        assert actual == expected
    else:
        # The old ad-high-cpu request is a frozen plain-BM25 research artifact.
        # Keep it as historical evidence, but exercise only the current structured contract here.
        assert actual["model"] == "openai/gpt-oss-120b"
        assert actual["response_format"]["json_schema"]["strict"] is True
        assert all(row["source_type"] == "HISTORY" for row in supplied["history"])
        assert all(row["source_type"] == "DOMAIN_KNOWLEDGE" for row in supplied["domain_knowledge"])


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
            usage={"prompt_tokens": 1, "completion_tokens": 1},
            latency_seconds=0.0,
            rate_limit_headers={},
            attempt_log=(),
        )


def _valid_hypothesis():
    return {
        "id": "H1",
        "explanation": "A source-faithful proposal may explain the observed condition.",
        "explains_fact_refs": ["F1"],
        "supporting_fact_refs": ["F1"],
        "history_refs": ["H1"],
        "knowledge_refs": ["K1"],
        "assumptions": ["A condition may be present."],
        "unresolved": ["Verify the condition."],
    }


def _small_context():
    from rca_ai.domain.models import Fact, FactEntity, HistoricalContext, KnowledgeItem
    from rca_ai.retrieval.history import HistoryRetrievalResult
    from rca_ai.retrieval.knowledge import KnowledgeRetrievalResult

    fact = Fact("F1", FactEntity("service", "svc"), "state", "error", "src", "/state")
    history = HistoryRetrievalResult(
        query="q", strategy="channel_bm25_rrf",
        items=(HistoricalContext("H1", "hist-1", {"incident_id": "hist-1"}),), metadata={},
    )
    knowledge = KnowledgeRetrievalResult(
        query="q", items=(KnowledgeItem("K1", "k-1", {"knowledge_key": "k-1", "claim": "general"}),),
        ranking=(("k-1", 0.5),),
    )
    return (fact,), history, knowledge


def test_zero_one_and_three_hypotheses_validate_and_preserve_text():
    facts, history, knowledge = _small_context()
    for rows in ([], [_valid_hypothesis()], [_valid_hypothesis()] + [
        {**_valid_hypothesis(), "id": f"H{i}"} for i in (2, 3)
    ]):
        provider = FakeProvider({"hypotheses": rows})
        result = HypothesisGenerator(provider).generate(facts, history, knowledge)
        assert len(result.hypotheses) == len(rows)
        if rows:
            assert isinstance(result.hypotheses[0], Hypothesis)
            assert result.hypotheses[0].explanation == rows[0]["explanation"]
            assert result.hypotheses[0].assumptions == tuple(rows[0]["assumptions"])
            assert result.hypotheses[0].unresolved == tuple(rows[0]["unresolved"])


@pytest.mark.parametrize(
    ("field", "bad_ref"),
    [("explains_fact_refs", "F404"), ("history_refs", "H404"), ("knowledge_refs", "K404")],
)
def test_unknown_references_fail_without_repair(field, bad_ref):
    facts, history, knowledge = _small_context()
    output = _valid_hypothesis()
    output[field] = [bad_ref]
    with pytest.raises(GenerationValidationError):
        HypothesisGenerator(FakeProvider({"hypotheses": [output]})).generate(
            facts, history, knowledge
        )


def test_duplicate_ids_and_more_than_three_hypotheses_fail():
    facts, history, knowledge = _small_context()
    duplicate = [_valid_hypothesis(), _valid_hypothesis()]
    with pytest.raises(GenerationValidationError):
        HypothesisGenerator(FakeProvider({"hypotheses": duplicate})).generate(facts, history, knowledge)
    too_many = [{**_valid_hypothesis(), "id": f"H{i}"} for i in range(4)]
    with pytest.raises(GenerationValidationError):
        HypothesisGenerator(FakeProvider({"hypotheses": too_many})).generate(facts, history, knowledge)


def test_duplicate_refs_and_excess_assumptions_fail():
    facts, history, knowledge = _small_context()
    duplicate_refs = _valid_hypothesis()
    duplicate_refs["supporting_fact_refs"] = ["F1", "F1"]
    with pytest.raises(GenerationValidationError):
        HypothesisGenerator(FakeProvider({"hypotheses": [duplicate_refs]})).generate(
            facts, history, knowledge
        )
    excess = _valid_hypothesis()
    excess["assumptions"] = ["a", "b", "c", "d"]
    with pytest.raises(GenerationValidationError):
        HypothesisGenerator(FakeProvider({"hypotheses": [excess]})).generate(
            facts, history, knowledge
        )


def test_invalid_schema_shape_fails_and_provider_error_is_not_wrapped():
    facts, history, knowledge = _small_context()
    with pytest.raises(GenerationValidationError):
        HypothesisGenerator(FakeProvider({"hypotheses": [{"id": "H1"}]})).generate(
            facts, history, knowledge
        )
    provider_error = ProviderError("transport failed", attempts=3)
    with pytest.raises(ProviderError) as raised:
        HypothesisGenerator(FakeProvider(error=provider_error)).generate(facts, history, knowledge)
    assert raised.value is provider_error
