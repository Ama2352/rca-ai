"""Offline contract tests for the no-Selector prepared-demo execution path."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from rca_ai.domain.models import IncidentInput, canonical_evidence_from_dict
from rca_ai.pipeline.prepared_demo import PreparedDemoPipeline
from rca_ai.pipeline.prepared_demo_providers import ProviderCallPacer
from rca_ai.pipeline.request_budget import RequestBudgetExceeded, request_size
from rca_ai.providers.groq import ProviderError, ProviderResult


PROJECT_ROOT = Path(__file__).resolve().parents[3]
FIXTURE_ROOT = PROJECT_ROOT / "data" / "demo"
SCENARIOS = (
    "missing-secret-01", "application-failure-01", "ad-high-cpu-01",
    "dependency-unavailable-01", "messaging-failure-01", "cart-failure-01",
    "memory-leak-01", "crash-loop-backoff-01", "downstream-latency-01",
)
FROZEN_RETRIEVAL_SCENARIOS = ("missing-secret-01", "application-failure-01", "ad-high-cpu-01")
NEW_SCENARIOS = (
    "dependency-unavailable-01", "messaging-failure-01", "cart-failure-01",
    "memory-leak-01", "crash-loop-backoff-01", "downstream-latency-01",
)
EXPECTED_HISTORY = {
    "missing-secret-01": ("H020", "H021", "H019"),
    "application-failure-01": ("H006", "H010", "H001"),
    "ad-high-cpu-01": ("H001", "H013", "H003"),
}
EXPECTED_KNOWLEDGE = {
    "missing-secret-01": (
        "kubernetes.pod_phase.pending",
        "kubernetes.container_state.waiting",
        "kubernetes.secret.required_startup",
    ),
    "application-failure-01": (
        "kubernetes.container_state.waiting",
        "kubernetes.pod_phase.pending",
        "kubernetes.secret.required_startup",
    ),
    "ad-high-cpu-01": (
        "kubernetes.container_state.waiting",
        "kubernetes.secret.required_startup",
        "kubernetes.pod_phase.pending",
    ),
}


def _load_incident(scenario: str) -> IncidentInput:
    payload = json.loads((FIXTURE_ROOT / f"{scenario}.json").read_text(encoding="utf-8"))
    return IncidentInput(payload["incident_id"], canonical_evidence_from_dict(payload["evidence"]))


def _provider_result(content: Any) -> ProviderResult:
    return ProviderResult(
        content=content,
        raw_content=json.dumps(content, ensure_ascii=False),
        http_status=200,
        attempts=1,
        response_id="offline-fixture",
        model_returned="offline-fixture",
        finish_reason="stop",
        usage={"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
        latency_seconds=0.0,
        rate_limit_headers={},
        attempt_log=(),
    )


def _request_payload(request: dict[str, Any]) -> dict[str, Any]:
    return json.loads(request["messages"][1]["content"])


class GeneratorProvider:
    def __init__(
        self,
        *,
        explanation: str = "A cautious candidate explanation.",
        empty: bool = False,
        error: BaseException | None = None,
        response: Any | None = None,
        events: list[str] | None = None,
    ):
        self.requests: list[dict[str, Any]] = []
        self.explanation = explanation
        self.empty = empty
        self.error = error
        self.response = response
        self.events = events

    def complete(self, request):
        self.requests.append(request)
        if self.events is not None:
            self.events.append("generator")
        if self.error is not None:
            raise self.error
        if self.response is not None:
            return _provider_result(self.response)
        if self.empty:
            return _provider_result({"hypotheses": []})
        payload = _request_payload(request)
        fact_refs = [row["fact_id"] for row in payload["current_facts"]]
        history_refs = [row["alias"] for row in payload["history"][:1]]
        knowledge_refs = [row["alias"] for row in payload["domain_knowledge"][:1]]
        candidates = []
        for candidate_id in ("HYP1", "HYP2"):
            candidates.append({
                "id": candidate_id,
                "explanation": self.explanation,
                "explains_fact_refs": fact_refs[:1],
                "supporting_fact_refs": fact_refs[:1],
                "history_refs": history_refs,
                "knowledge_refs": knowledge_refs,
                "assumptions": [],
                "unresolved": [],
            })
        return _provider_result({"hypotheses": candidates})


class ValidatorProvider:
    def __init__(
        self,
        *,
        error: BaseException | None = None,
        response: Any | None = None,
        events: list[str] | None = None,
    ):
        self.requests: list[dict[str, Any]] = []
        self.error = error
        self.response = response
        self.events = events

    def complete(self, request):
        self.requests.append(request)
        if self.events is not None:
            self.events.append("validator")
        if self.error is not None:
            raise self.error
        if self.response is not None:
            return _provider_result(self.response)
        payload = _request_payload(request)
        fact_refs = [row["fact_id"] for row in payload["current_facts"]]
        hypothesis_id = payload["candidate_hypothesis"]["id"]
        first_ref = fact_refs[:1]
        return _provider_result({
            "hypothesis_id": hypothesis_id,
            "decision": "KEEP_QUALIFIED",
            "support_level": "PLAUSIBLE",
            "incident_basis": {"evidence": first_ref},
            "hard_violations": [],
            "qualifications": [],
            "relation_assessment": {
                "relation": "May explain the observation.",
                "support_level": "PLAUSIBLE",
                "fact_refs": first_ref,
                "reason": "Causal support remains uncertain.",
            },
            "unresolved": [],
        })


class RecoverOnceValidatorProvider:
    """Fail once with Groq's structured schema error, then return valid data."""

    def __init__(self):
        self.requests = []

    def complete(self, request):
        from rca_ai.providers.groq import ProviderHTTPError

        self.requests.append(request)
        if len(self.requests) == 1:
            raise ProviderHTTPError(
                "structured output rejected",
                attempts=1,
                status_code=400,
                response_detail=json.dumps({
                    "error": {
                        "type": "invalid_request_error",
                        "code": "json_validate_failed",
                    }
                }),
            )
        payload = _request_payload(request)
        refs = [row["fact_id"] for row in payload["current_facts"]]
        return _provider_result({
            "hypothesis_id": payload["candidate_hypothesis"]["id"],
            "decision": "KEEP_QUALIFIED",
            "support_level": "PLAUSIBLE",
            "incident_basis": {"evidence": refs[:1]},
            "hard_violations": [],
            "qualifications": [{
                "claim": "a causal relation",
                "issue": "causation is not established",
                "fact_refs": refs[:1],
                "observed_form": "the observations co-occur",
            }],
            "relation_assessment": {
                "relation": "may explain",
                "support_level": "PLAUSIBLE",
                "fact_refs": refs[:1],
                "reason": "the relation remains uncertain",
            },
            "unresolved": [],
        })


def _expected_fact_payload(facts):
    return [
        {
            "fact_id": fact.fact_id,
            "source_ref": fact.source_ref,
            "entity": {"type": fact.entity.type, "id": fact.entity.id},
            "field": fact.field,
            "value": fact.value,
            "source_path": fact.source_path,
        }
        for fact in facts
    ]


@pytest.mark.parametrize("scenario", SCENARIOS)
def test_prepared_demo_passes_every_unchanged_fact_to_generator_and_validators(scenario):
    generator = GeneratorProvider()
    validator = ValidatorProvider()
    pipeline = PreparedDemoPipeline(generator_provider=generator, validator_provider=validator)

    result = pipeline.run(_load_incident(scenario))

    expected_facts = _expected_fact_payload(result.facts)
    generator_facts = _request_payload(generator.requests[0])["current_facts"]
    assert generator_facts == expected_facts
    assert result.fact_integrity
    assert len(result.facts) == len(result.evidence.observations)
    for index, (fact, observation) in enumerate(zip(result.facts, result.evidence.observations, strict=True), 1):
        assert fact.fact_id == f"F{index}"
        assert fact.entity.type == observation.entity.type
        assert fact.entity.id == observation.entity.id
        assert fact.field == observation.field
        assert fact.value == observation.value
        assert fact.source_ref == observation.source.source_ref
        assert fact.source_path == observation.source.source_path
    assert result.generation.request == generator.requests[0]
    assert len(validator.requests) == 2
    for request in validator.requests:
        assert _request_payload(request)["current_facts"] == expected_facts
    assert result.rca_result.incident_id == scenario


@pytest.mark.parametrize("scenario", FROZEN_RETRIEVAL_SCENARIOS)
def test_prepared_demo_replays_frozen_retrieval_and_full_requests_fit(scenario):
    generator = GeneratorProvider()
    validator = ValidatorProvider()
    result = PreparedDemoPipeline(
        generator_provider=generator,
        validator_provider=validator,
    ).run(_load_incident(scenario))

    assert tuple(item.source_id for item in result.history.items) == EXPECTED_HISTORY[scenario]
    assert tuple(item.source_id for item in result.knowledge.items) == EXPECTED_KNOWLEDGE[scenario]
    assert result.retrieval_projection.query == result.history.query == result.knowledge.query
    assert len(result.generation.request["messages"][1]["content"].encode("utf-8")) > 0
    requests = [result.generation.request, *(execution.request for execution in result.validations)]
    assert len(requests) == 3
    assert all(request_size(request)[1] <= 7000 for request in requests)
    assert all(execution.provider_result.http_status == 200 for execution in result.validations)


@pytest.mark.parametrize("scenario", NEW_SCENARIOS)
def test_new_prepared_scenarios_keep_fact_and_hk_references_resolved_within_budget(scenario):
    generator = GeneratorProvider()
    validator = ValidatorProvider()
    result = PreparedDemoPipeline(generator_provider=generator, validator_provider=validator).run(_load_incident(scenario))
    fact_ids = {fact.fact_id for fact in result.facts}
    history_ids = {item.alias for item in result.history.items}
    knowledge_ids = {item.alias for item in result.knowledge.items}
    assert result.fact_integrity
    assert len(result.facts) == len(result.evidence.observations)
    for candidate in result.rca_result.candidate_results:
        assert set(candidate.evidence_refs) <= fact_ids
        assert set(candidate.history_refs) <= history_ids
        assert set(candidate.knowledge_refs) <= knowledge_ids
    requests = [result.generation.request, *(execution.request for execution in result.validations)]
    assert all(request_size(request)[1] <= 7000 for request in requests)


def test_optional_observer_reports_actual_stages_without_changing_output():
    incident = _load_incident("missing-secret-01")
    plain = PreparedDemoPipeline(
        generator_provider=GeneratorProvider(), validator_provider=ValidatorProvider(),
    ).run(incident)
    events = []
    observed = PreparedDemoPipeline(
        generator_provider=GeneratorProvider(), validator_provider=ValidatorProvider(),
    ).run(incident, observer=events.append)

    assert observed == plain
    assert [(event.kind, event.stage, event.candidate_id) for event in events] == [
        ("stage_started", "evidence", None), ("stage_completed", "evidence", None),
        ("stage_started", "retrieval", None), ("stage_completed", "retrieval", None),
        ("stage_started", "generation", None), ("provider_started", "generation", None),
        ("provider_completed", "generation", None), ("stage_completed", "generation", None),
        ("stage_started", "validation", "HYP1"), ("provider_started", "validation", "HYP1"),
        ("provider_completed", "validation", "HYP1"), ("stage_completed", "validation", "HYP1"),
        ("stage_started", "validation", "HYP2"), ("provider_started", "validation", "HYP2"),
        ("provider_completed", "validation", "HYP2"), ("stage_completed", "validation", "HYP2"),
        ("stage_started", "assembly", None), ("stage_completed", "assembly", None),
    ]
    assert all(event.timestamp >= 0 for event in events)


def test_observer_reports_only_explicit_pacer_waits_as_pacing():
    events = []
    pipeline = PreparedDemoPipeline(
        generator_provider=GeneratorProvider(), validator_provider=ValidatorProvider(),
        provider_pacer=ProviderCallPacer(fallback_delay_seconds=0.01, sleep=lambda _: None),
    )

    pipeline.run(_load_incident("missing-secret-01"), observer=events.append)

    pacing = [(event.kind, event.stage, event.candidate_id) for event in events if event.kind.startswith("pacing_")]
    assert pacing == [
        ("pacing_started", "validation", "HYP1"),
        ("pacing_completed", "validation", "HYP1"),
        ("pacing_started", "validation", "HYP2"),
        ("pacing_completed", "validation", "HYP2"),
    ]


def test_prepared_demo_repeats_deterministic_stages_identically():
    incident = _load_incident("application-failure-01")
    first = PreparedDemoPipeline(generator_provider=GeneratorProvider(), validator_provider=ValidatorProvider()).run(incident)
    second = PreparedDemoPipeline(generator_provider=GeneratorProvider(), validator_provider=ValidatorProvider()).run(incident)

    assert first.facts == second.facts
    assert first.retrieval_projection == second.retrieval_projection
    assert first.history.items == second.history.items
    assert first.knowledge.items == second.knowledge.items
    assert first.generation.request == second.generation.request
    assert first.rca_result == second.rca_result


def test_prepared_demo_preserves_frozen_stage_order(monkeypatch):
    import rca_ai.pipeline.prepared_demo as prepared_demo

    events: list[str] = []
    for function_name, event in (
        ("build_fact_view", "build"),
        ("verify_fact_view", "verify"),
        ("project_retrieval", "project"),
        ("retrieve_history", "history"),
        ("retrieve_knowledge", "knowledge"),
        ("assemble_result", "assemble"),
    ):
        original = getattr(prepared_demo, function_name)

        def wrapped(*args, __original=original, __event=event, **kwargs):
            events.append(__event)
            return __original(*args, **kwargs)

        monkeypatch.setattr(prepared_demo, function_name, wrapped)

    generator = GeneratorProvider(events=events)
    validator = ValidatorProvider(events=events)
    PreparedDemoPipeline(generator_provider=generator, validator_provider=validator).run(
        _load_incident("missing-secret-01")
    )

    assert events == [
        "build", "verify", "project", "history", "knowledge",
        "generator", "validator", "validator", "assemble",
    ]


def test_prepared_demo_never_invokes_selector(monkeypatch):
    from rca_ai.facts import selector

    def forbidden(*args, **kwargs):
        raise AssertionError("prepared demo must not invoke Fact Selector")

    monkeypatch.setattr(selector, "select_facts", forbidden)
    pipeline = PreparedDemoPipeline(generator_provider=GeneratorProvider(), validator_provider=ValidatorProvider())

    pipeline.run(_load_incident("missing-secret-01"))


def test_prepared_demo_recovers_validator_schema_error_without_regenerating_or_changing_facts():
    generator = GeneratorProvider()
    validator = RecoverOnceValidatorProvider()
    incident = _load_incident("missing-secret-01")

    result = PreparedDemoPipeline(
        generator_provider=generator,
        validator_provider=validator,
    ).run(incident)

    expected_facts = _expected_fact_payload(result.facts)
    assert len(generator.requests) == 1
    assert len(validator.requests) == 3  # one retry for HYP1, then one call for HYP2
    assert validator.requests[0] is validator.requests[1]
    assert validator.requests[2] is not validator.requests[1]
    assert all(_request_payload(request)["current_facts"] == expected_facts for request in validator.requests)
    assert [execution.result.decision.value for execution in result.validations] == [
        "KEEP_QUALIFIED",
        "KEEP_QUALIFIED",
    ]
    assert result.fact_integrity
    assert len(result.facts) == len(incident.evidence.observations)


def test_prepared_demo_pacing_is_shared_between_generator_and_validator_calls():
    from rca_ai.pipeline.prepared_demo_providers import ProviderCallPacer

    delays = []
    pipeline = PreparedDemoPipeline(
        generator_provider=GeneratorProvider(),
        validator_provider=ValidatorProvider(),
        provider_pacer=ProviderCallPacer(fallback_delay_seconds=75, sleep=delays.append),
    )

    pipeline.run(_load_incident("missing-secret-01"))

    # Two hypotheses mean one Generator->Validator interval and one
    # Validator->Validator interval. The first provider call is immediate.
    assert delays == [75, 75]


def test_default_pipeline_does_not_use_prepared_demo_schema_recovery():
    from rca_ai.pipeline.orchestrator import RCAPipeline
    from rca_ai.reasoning.generator import HypothesisGenerator
    from rca_ai.reasoning.validator import HypothesisValidator
    from rca_ai.providers.groq import ProviderHTTPError

    class AlwaysSchemaErrorProvider:
        def __init__(self):
            self.calls = 0

        def complete(self, request):
            self.calls += 1
            raise ProviderHTTPError(
                "structured output rejected",
                attempts=1,
                status_code=400,
                response_detail=json.dumps({
                    "error": {
                        "type": "invalid_request_error",
                        "code": "json_validate_failed",
                    }
                }),
            )

    validator_provider = AlwaysSchemaErrorProvider()
    pipeline = RCAPipeline(
        generator=HypothesisGenerator(GeneratorProvider()),
        validator=HypothesisValidator(validator_provider),
    )

    with pytest.raises(ProviderHTTPError):
        pipeline.run(_load_incident("missing-secret-01"))

    assert validator_provider.calls == 1


def test_oversize_generator_request_fails_before_provider_call():
    generator = GeneratorProvider()
    validator = ValidatorProvider()
    pipeline = PreparedDemoPipeline(
        generator_provider=generator,
        validator_provider=validator,
        max_estimated_tokens=1,
    )

    with pytest.raises(RequestBudgetExceeded):
        pipeline.run(_load_incident("missing-secret-01"))

    assert generator.requests == []
    assert validator.requests == []


def test_oversize_validator_request_fails_before_that_provider_call():
    generator = GeneratorProvider(explanation="x" * 30_000)
    validator = ValidatorProvider()
    pipeline = PreparedDemoPipeline(
        generator_provider=generator,
        validator_provider=validator,
        max_estimated_tokens=7000,
    )

    with pytest.raises(RequestBudgetExceeded):
        pipeline.run(_load_incident("missing-secret-01"))

    assert len(generator.requests) == 1
    assert validator.requests == []


def test_zero_hypotheses_is_valid_abstention_without_validator_calls():
    generator = GeneratorProvider(empty=True)
    validator = ValidatorProvider()
    result = PreparedDemoPipeline(generator_provider=generator, validator_provider=validator).run(
        _load_incident("missing-secret-01")
    )

    assert len(generator.requests) == 1
    assert validator.requests == []
    assert result.validations == ()
    assert result.rca_result.candidate_results == ()


def test_provider_and_response_contract_errors_propagate():
    failed_generator = GeneratorProvider(error=ProviderError("failed", attempts=1))
    pipeline = PreparedDemoPipeline(generator_provider=failed_generator, validator_provider=ValidatorProvider())
    with pytest.raises(ProviderError):
        pipeline.run(_load_incident("missing-secret-01"))

    malformed_generator = GeneratorProvider(response={"hypotheses": [{"id": "invalid"}]})
    pipeline = PreparedDemoPipeline(generator_provider=malformed_generator, validator_provider=ValidatorProvider())
    with pytest.raises(ValueError, match="Generator output"):
        pipeline.run(_load_incident("missing-secret-01"))

    generator = GeneratorProvider()
    invalid_validator = ValidatorProvider(error=ProviderError("validator failed", attempts=1))
    pipeline = PreparedDemoPipeline(generator_provider=generator, validator_provider=invalid_validator)
    with pytest.raises(ProviderError):
        pipeline.run(_load_incident("missing-secret-01"))

    invalid_validator = ValidatorProvider(response={"hypothesis_id": "wrong"})
    pipeline = PreparedDemoPipeline(generator_provider=GeneratorProvider(), validator_provider=invalid_validator)
    with pytest.raises(ValueError, match="Validator output"):
        pipeline.run(_load_incident("missing-secret-01"))


def test_pipeline_module_exports_prepared_demo_without_changing_default_runner():
    from rca_ai.pipeline import PreparedDemoPipeline as exported
    from rca_ai.pipeline.orchestrator import RCAPipeline

    assert exported is PreparedDemoPipeline
    assert callable(RCAPipeline.run)
