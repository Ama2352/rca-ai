"""Frozen orchestration tests using only local fixtures and fake providers."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from rca_ai.domain.models import IncidentInput, to_dict
from rca_ai.pipeline.orchestrator import RCAPipeline
from rca_ai.providers.groq import ProviderError, ProviderResult
from rca_ai.reasoning.generator import HypothesisGenerator
from rca_ai.reasoning.generator import GenerationValidationError
from rca_ai.reasoning.validator import HypothesisValidator, ValidatorValidationError


ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "fixtures"
SCENARIOS = ("missing-secret-01", "application-failure-01", "ad-high-cpu-01")
RETRIEVAL_INPUTS = {
    "missing-secret-01": FIXTURES / "retrieval" / "inputs" / "channel-incident-01.json",
    "application-failure-01": FIXTURES / "retrieval" / "inputs" / "channel-incident-02.json",
    "ad-high-cpu-01": FIXTURES / "retrieval" / "inputs" / "plain-query.txt",
}


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _incident(scenario: str) -> IncidentInput:
    normalized = _read_json(FIXTURES / "facts" / "inputs" / f"{scenario}.normalized.json")
    retrieval_path = RETRIEVAL_INPUTS[scenario]
    retrieval = (
        retrieval_path.read_text(encoding="utf-8")
        if retrieval_path.suffix == ".txt"
        else _read_json(retrieval_path)
    )
    return IncidentInput(scenario, normalized, retrieval)


def _provider_result(content: Any) -> ProviderResult:
    return ProviderResult(
        content=content,
        raw_content=json.dumps(content, ensure_ascii=False),
        http_status=200,
        attempts=1,
        response_id="fixture",
        model_returned="fixture-model",
        finish_reason="stop",
        usage={"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
        latency_seconds=0.0,
        rate_limit_headers={},
        attempt_log=(),
    )


class QueueProvider:
    def __init__(self, outputs: list[Any], calls: list[dict[str, Any]] | None = None, events=None, label=None):
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


def _fake_pipeline(scenario: str, events=None) -> tuple[RCAPipeline, QueueProvider, QueueProvider]:
    generation = _read_json(
        FIXTURES / "reasoning" / "validator" / "inputs" / f"{scenario}.generation.json"
    )
    ids = [row["id"] for row in generation["hypotheses"]]
    validations = [
        _read_json(
            FIXTURES / "reasoning" / "validator" / "expected" / scenario / f"{hypothesis_id}.response.json"
        )
        for hypothesis_id in ids
    ]
    generation_provider = QueueProvider([generation], events=events, label="generator")
    validation_provider = QueueProvider(validations, events=events, label="validator")
    return (
        RCAPipeline(
            generator=HypothesisGenerator(generation_provider),
            validator=HypothesisValidator(validation_provider),
        ),
        generation_provider,
        validation_provider,
    )


@pytest.mark.parametrize("scenario", SCENARIOS)
def test_mocked_frozen_pipeline_matches_exact_final_result(scenario: str, monkeypatch: pytest.MonkeyPatch):
    """The orchestration wiring reproduces the three frozen results without network calls."""
    import rca_ai.pipeline.orchestrator as orchestrator

    events: list[str] = []
    assembly_calls: list[tuple[Any, ...]] = []
    for name, event in (
        ("build_fact_view", "build"),
        ("verify_fact_view", "verify"),
        ("retrieve_history", "history"),
        ("retrieve_knowledge", "knowledge"),
        ("select_facts", "select"),
        ("assemble_result", "assemble"),
    ):
        original = getattr(orchestrator, name)

        def wrapper(*args, __original=original, __event=event, **kwargs):
            events.append(__event)
            if __event == "assemble":
                assembly_calls.append(args)
            return __original(*args, **kwargs)

        monkeypatch.setattr(orchestrator, name, wrapper)

    original_request_builder = orchestrator.build_generator_request

    def tracked_request_builder(facts, history, knowledge):
        assert history.items and knowledge.items
        events.append("request_size")
        return original_request_builder(facts, history, knowledge)

    monkeypatch.setattr(orchestrator, "build_generator_request", tracked_request_builder)

    pipeline, generator_provider, validator_provider = _fake_pipeline(scenario, events)
    run = pipeline.run(_incident(scenario))

    expected = _read_json(FIXTURES / "pipeline" / "assembler" / f"{scenario}.final_result.json")
    assert to_dict(run.rca_result) == expected
    assert run.fact_integrity is True
    assert run.selection.full_fact_count == len(run.facts)
    assert run.selection.selected_fact_count == len(run.selection.facts)
    assert len(generator_provider.calls) == 1
    assert len(validator_provider.calls) == len(run.generation.hypotheses)
    assert [item.result.hypothesis_id for item in run.validations] == [
        item.id for item in run.generation.hypotheses
    ]
    assert events.index("build") < events.index("verify") < events.index("history")
    assert events.index("history") < events.index("knowledge") < events.index("select")
    assert events.index("select") < events.index("request_size") < events.index("generator")
    assert events.index("generator") < events.index("validator") < events.index("assemble")
    assert events.count("validator") == len(run.generation.hypotheses)
    assert assembly_calls[0][1] == run.generation.hypotheses
    assert assembly_calls[0][2] == tuple(execution.result for execution in run.validations)
    assert assembly_calls[0][3] == run.selection.facts
    assert len(run.history.items) > 0


def test_selector_sizes_exact_generator_request_after_fresh_retrieval():
    """Request-size decisions include the fresh H/K context and exact request builder."""
    from rca_ai.facts.selector import request_bytes
    from rca_ai.reasoning.generator import build_generator_request

    pipeline, _, _ = _fake_pipeline("application-failure-01")
    run = pipeline.run(_incident("application-failure-01"))
    assert run.selection.full_request_bytes == request_bytes(
        build_generator_request(run.facts, run.history, run.knowledge)
    )
    assert run.selection.selected_request_bytes == request_bytes(
        build_generator_request(run.selection.facts, run.history, run.knowledge)
    )
    assert run.selection.selector_used


def test_core_run_writes_no_artifacts(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Artifact persistence belongs to a later runner, not core orchestration."""
    monkeypatch.chdir(tmp_path)
    pipeline, _, _ = _fake_pipeline("missing-secret-01")
    before = tuple(tmp_path.iterdir())
    pipeline.run(_incident("missing-secret-01"))
    assert tuple(tmp_path.iterdir()) == before == ()


def test_zero_hypotheses_is_valid_abstention_without_validator_calls():
    generator_provider = QueueProvider([{"hypotheses": []}])
    validator_provider = QueueProvider([])
    pipeline = RCAPipeline(
        generator=HypothesisGenerator(generator_provider),
        validator=HypothesisValidator(validator_provider),
    )
    run = pipeline.run(_incident("missing-secret-01"))
    assert len(generator_provider.calls) == 1
    assert validator_provider.calls == []
    assert run.validations == ()
    assert to_dict(run.rca_result) == {"incident_id": "missing-secret-01", "candidate_results": []}


def test_missing_retrieval_input_fails_before_fact_or_provider_work():
    pipeline, generator_provider, validator_provider = _fake_pipeline("missing-secret-01")
    incident = IncidentInput("no-query", _incident("missing-secret-01").normalized_evidence)
    with pytest.raises(ValueError, match="retrieval_input is required"):
        pipeline.run(incident)
    assert generator_provider.calls == []
    assert validator_provider.calls == []


@pytest.mark.parametrize(
    ("generator_output", "expected_error"),
    [
        (ProviderError("transport failure", attempts=1), ProviderError),
        ({"hypotheses": [{"id": "bad"}]}, GenerationValidationError),
    ],
)
def test_generator_failures_propagate_without_semantic_retry(generator_output, expected_error):
    provider = QueueProvider([generator_output])
    pipeline = RCAPipeline(
        generator=HypothesisGenerator(provider),
        validator=HypothesisValidator(QueueProvider([])),
    )
    with pytest.raises(expected_error):
        pipeline.run(_incident("missing-secret-01"))
    assert len(provider.calls) == 1


@pytest.mark.parametrize(
    ("validator_output", "expected_error"),
    [
        (ProviderError("transport failure", attempts=1), ProviderError),
        ({"hypothesis_id": "wrong"}, ValidatorValidationError),
    ],
)
def test_validator_failures_propagate_without_semantic_retry(validator_output, expected_error):
    generation = _read_json(
        FIXTURES / "reasoning" / "validator" / "inputs" / "missing-secret-01.generation.json"
    )
    generator_provider = QueueProvider([generation])
    validator_provider = QueueProvider([validator_output])
    pipeline = RCAPipeline(
        generator=HypothesisGenerator(generator_provider),
        validator=HypothesisValidator(validator_provider),
    )
    with pytest.raises(expected_error):
        pipeline.run(_incident("missing-secret-01"))
    assert len(generator_provider.calls) == 1
    assert len(validator_provider.calls) == 1
