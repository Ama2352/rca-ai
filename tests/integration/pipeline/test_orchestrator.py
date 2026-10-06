"""Pipeline wiring tests with canonical evidence and fake semantic providers."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from rca_ai.domain.models import (
    CanonicalIncidentEvidence, CanonicalObservation, EvidenceEntity, EvidenceSource,
    IncidentInput, to_dict,
)
from rca_ai.pipeline.orchestrator import RCAPipeline
from rca_ai.providers.groq import ProviderError, ProviderResult
from rca_ai.reasoning.generator import GenerationValidationError, HypothesisGenerator
from rca_ai.reasoning.validator import HypothesisValidator, ValidatorValidationError


ROOT = Path(__file__).resolve().parents[2]
SCENARIOS = ("missing-secret-01", "application-failure-01", "ad-high-cpu-01")


def _incident(scenario: str) -> IncidentInput:
    observation = CanonicalObservation(
        observation_id="obs-1", signal="metric", entity=EvidenceEntity("service", "checkout"),
        field="metric.counter_rate", value={
            "lane": "metric.counter_rate", "service": "checkout", "metric": "requests_total",
            "metric_kind": "counter", "labels": {}, "unit": "events/second",
            "baseline_value": 10.0, "incident_value": 20.0, "signed_change": 10.0,
            "change": "increased", "uncertainty": [],
        }, attributes={}, source=EvidenceSource("src-1", "/metrics/0", ("metrics.json:rows[0]",)),
    )
    return IncidentInput(scenario, CanonicalIncidentEvidence({}, (observation,)))


def _provider_result(content: Any) -> ProviderResult:
    return ProviderResult(
        content=content, raw_content=json.dumps(content, ensure_ascii=False), http_status=200,
        attempts=1, response_id="fixture", model_returned="fixture-model", finish_reason="stop",
        usage={"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
        latency_seconds=0.0, rate_limit_headers={}, attempt_log=(),
    )


class QueueProvider:
    def __init__(self, outputs, calls=None, events=None, label=None):
        self.outputs = list(outputs)
        self.calls = calls if calls is not None else []
        self.events = events
        self.label = label

    def complete(self, request):
        self.calls.append(request)
        if self.events is not None:
            self.events.append(self.label)
        if not self.outputs:
            raise AssertionError("unexpected semantic provider call")
        output = self.outputs.pop(0)
        if isinstance(output, BaseException):
            raise output
        return _provider_result(output)


def _generation():
    return {"hypotheses": [{
        "id": "HYP1", "explanation": "The observed request-rate change may explain the incident.",
        "explains_fact_refs": ["F1"], "supporting_fact_refs": ["F1"],
        "history_refs": [], "knowledge_refs": [], "assumptions": [], "unresolved": [],
    }]}


def _validation():
    return {
        "hypothesis_id": "HYP1", "decision": "KEEP_QUALIFIED", "support_level": "PLAUSIBLE",
        "incident_basis": {"evidence": ["F1"]}, "hard_violations": [], "qualifications": [],
        "relation_assessment": {"relation": "May explain the rate change.", "support_level": "PLAUSIBLE",
                                "fact_refs": ["F1"], "reason": "The causal relation remains uncertain."},
        "unresolved": [],
    }


def _fake_pipeline(events=None, generation=None, validation=None):
    gen = QueueProvider([generation if generation is not None else _generation()], events=events, label="generator")
    val = QueueProvider([validation if validation is not None else _validation()], events=events, label="validator")
    return RCAPipeline(generator=HypothesisGenerator(gen), validator=HypothesisValidator(val)), gen, val


@pytest.mark.parametrize("scenario", SCENARIOS)
def test_canonical_incident_completes_pipeline_and_keeps_provenance_namespaces(scenario):
    pipeline, gen, val = _fake_pipeline()
    run = pipeline.run(_incident(scenario))

    assert run.fact_integrity
    assert run.retrieval_projection.query == run.history.query == run.knowledge.query
    assert run.facts[0].source_ref == "src-1"
    assert run.rca_result.candidate_results[0].evidence_refs == ("F1",)
    assert run.rca_result.candidate_results[0].hypothesis.explanation == _generation()["hypotheses"][0]["explanation"]
    assert len(gen.calls) == len(val.calls) == 1


def test_multiple_candidates_validate_and_assemble_in_generator_order():
    first = _generation()["hypotheses"][0]
    second = {**first, "id": "HYP2", "explanation": "A competing explanation remains possible."}
    first_validation = _validation()
    second_validation = {**first_validation, "hypothesis_id": "HYP2", "decision": "KEEP"}
    generator = QueueProvider([{"hypotheses": [first, second]}])
    validator = QueueProvider([first_validation, second_validation])
    pipeline = RCAPipeline(
        generator=HypothesisGenerator(generator),
        validator=HypothesisValidator(validator),
    )

    run = pipeline.run(_incident("contract-test"))

    assert len(generator.calls) == 1
    assert len(validator.calls) == 2
    validator_candidate_ids = [
        json.loads(request["messages"][1]["content"])["candidate_hypothesis"]["id"]
        for request in validator.calls
    ]
    assert validator_candidate_ids == ["HYP1", "HYP2"]
    assert [execution.result.hypothesis_id for execution in run.validations] == ["HYP1", "HYP2"]
    assert [item.hypothesis.id for item in run.rca_result.candidate_results] == ["HYP1", "HYP2"]
    assert all(item.evidence_refs == ("F1",) for item in run.rca_result.candidate_results)
    assert all(item.evidence_refs[0] in {fact.fact_id for fact in run.selection.facts} for item in run.rca_result.candidate_results)


def test_exact_stage_order_uses_fresh_internal_retrieval_projection(monkeypatch):
    import rca_ai.pipeline.orchestrator as orchestrator

    events = []
    for name, event in (
        ("build_fact_view", "build"), ("verify_fact_view", "verify"),
        ("project_retrieval", "project"), ("retrieve_history", "history"),
        ("retrieve_knowledge", "knowledge"), ("select_facts", "select"),
        ("assemble_result", "assemble"),
    ):
        original = getattr(orchestrator, name)

        def wrapper(*args, __original=original, __event=event, **kwargs):
            events.append(__event)
            return __original(*args, **kwargs)
        monkeypatch.setattr(orchestrator, name, wrapper)

    original_builder = orchestrator.build_generator_request
    def request_builder(*args, **kwargs):
        events.append("request_size")
        return original_builder(*args, **kwargs)
    monkeypatch.setattr(orchestrator, "build_generator_request", request_builder)

    pipeline, gen, val = _fake_pipeline(events)
    pipeline.run(_incident("contract-test"))
    assert events.index("build") < events.index("verify") < events.index("project")
    assert events.index("project") < events.index("history") < events.index("knowledge") < events.index("select")
    assert events.index("select") < events.index("request_size") < events.index("generator")
    assert events.index("generator") < events.index("validator") < events.index("assemble")
    assert len(gen.calls) == len(val.calls) == 1


def test_zero_hypotheses_is_valid_abstention_without_validator_calls():
    gen = QueueProvider([{"hypotheses": []}])
    val = QueueProvider([])
    run = RCAPipeline(generator=HypothesisGenerator(gen), validator=HypothesisValidator(val)).run(
        _incident("contract-test")
    )
    assert len(gen.calls) == 1 and val.calls == [] and run.validations == ()
    assert to_dict(run.rca_result) == {"incident_id": "contract-test", "candidate_results": []}


def test_selector_request_sizing_uses_exact_generator_request_after_retrieval():
    from rca_ai.facts.selector import request_bytes
    from rca_ai.reasoning.generator import build_generator_request
    pipeline, _, _ = _fake_pipeline()
    run = pipeline.run(_incident("contract-test"))
    assert run.selection.full_request_bytes == request_bytes(build_generator_request(run.facts, run.history, run.knowledge))
    assert run.selection.selected_request_bytes == request_bytes(build_generator_request(run.selection.facts, run.history, run.knowledge))


def test_core_run_writes_no_artifacts(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    pipeline, _, _ = _fake_pipeline()
    pipeline.run(_incident("contract-test"))
    assert tuple(tmp_path.iterdir()) == ()


@pytest.mark.parametrize(
    ("generator_output", "expected_error"),
    [(ProviderError("transport failure", attempts=1), ProviderError),
     ({"hypotheses": [{"id": "bad"}]}, GenerationValidationError)],
)
def test_generator_failures_propagate_without_semantic_retry(generator_output, expected_error):
    provider = QueueProvider([generator_output])
    pipeline = RCAPipeline(generator=HypothesisGenerator(provider), validator=HypothesisValidator(QueueProvider([])))
    with pytest.raises(expected_error):
        pipeline.run(_incident("contract-test"))
    assert len(provider.calls) == 1


@pytest.mark.parametrize(
    ("validator_output", "expected_error"),
    [(ProviderError("transport failure", attempts=1), ProviderError),
     ({"hypothesis_id": "wrong"}, ValidatorValidationError)],
)
def test_validator_failures_propagate_without_semantic_retry(validator_output, expected_error):
    generator = QueueProvider([_generation()])
    validator = QueueProvider([validator_output])
    pipeline = RCAPipeline(generator=HypothesisGenerator(generator), validator=HypothesisValidator(validator))
    with pytest.raises(expected_error):
        pipeline.run(_incident("contract-test"))
    assert len(generator.calls) == len(validator.calls) == 1
