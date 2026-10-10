"""Deterministic three-capture bridge test (semantic providers are local fakes)."""

from __future__ import annotations

from dataclasses import asdict
import json
from pathlib import Path
import sys

import pytest

from rca_ai.domain.models import IncidentInput, canonical_evidence_from_dict
from rca_ai.pipeline.orchestrator import RCAPipeline
from rca_ai.providers.contracts import ProviderResult
from rca_ai.retrieval.history import retrieve_history
from rca_ai.retrieval.knowledge import retrieve_knowledge
from rca_ai.retrieval.projection import project_retrieval


PROJECT_ROOT = Path(__file__).resolve().parents[3]
PROCESSOR_ROOT = PROJECT_ROOT.parent / "otel_demo_dataset"
CAPTURE_ROOT = PROCESSOR_ROOT / "otel_demo_dataset" / "pilot"
SCENARIOS = {
    "missing-secret-01": {"metric": 17, "log": 0, "trace": 0, "kubernetes": 2},
    "application-failure-01": {"metric": 28, "log": 7, "trace": 18, "kubernetes": 0},
    "ad-high-cpu-01": {"metric": 2, "log": 5, "trace": 7, "kubernetes": 0},
}


def _result(content):
    return ProviderResult(
        content=content, raw_content=json.dumps(content), http_status=200, attempts=1,
        response_id="local-fixture", model_returned="local-fixture", finish_reason="stop",
        usage={}, latency_seconds=0.0, rate_limit_headers={}, attempt_log=(),
    )


class FakeSemanticProvider:
    def __init__(self, stage):
        self.stage = stage
        self.calls = []

    def complete(self, request):
        self.calls.append(request)
        payload = json.loads(request["messages"][1]["content"])
        fact_id = payload["current_facts"][0]["fact_id"]
        if self.stage == "generator":
            content = {"hypotheses": [{
                "id": "HYP1", "explanation": "The observed condition may be relevant to this incident.",
                "explains_fact_refs": [fact_id], "supporting_fact_refs": [fact_id],
                "history_refs": [], "knowledge_refs": [], "assumptions": [], "unresolved": [],
            }]}
        else:
            candidate = payload["candidate_hypothesis"]
            content = {
                "hypothesis_id": candidate["id"], "decision": "KEEP_QUALIFIED", "support_level": "PLAUSIBLE",
                "incident_basis": {"evidence": [fact_id]}, "hard_violations": [], "qualifications": [],
                "relation_assessment": {
                    "relation": "The observed condition may be relevant.", "support_level": "PLAUSIBLE",
                    "fact_refs": [fact_id], "reason": "Causality remains unresolved.",
                },
                "unresolved": [],
            }
        return _result(content)


def _load_processor():
    if str(PROCESSOR_ROOT) not in sys.path:
        sys.path.insert(0, str(PROCESSOR_ROOT))
    from rca_processor_v1_1 import process_capture_canonical

    return process_capture_canonical


@pytest.mark.parametrize("scenario,expected_signals", SCENARIOS.items())
def test_saved_capture_runs_through_canonical_processor_and_core(scenario, expected_signals):
    processed = _load_processor()(CAPTURE_ROOT / scenario)
    evidence_wire = json.loads(json.dumps(asdict(processed), ensure_ascii=False))
    evidence = canonical_evidence_from_dict(evidence_wire)
    signal_counts = {
        signal: sum(row.signal == signal for row in evidence.observations)
        for signal in expected_signals
    }
    assert signal_counts == expected_signals

    generator_provider = FakeSemanticProvider("generator")
    validator_provider = FakeSemanticProvider("validator")
    run = RCAPipeline(
        generator_provider=generator_provider,
        validator_provider=validator_provider,
    ).run(IncidentInput(scenario, evidence))

    assert run.fact_integrity
    assert len(run.facts) == len(evidence.observations)
    assert len({fact.source_ref for fact in run.facts}) == len(run.facts)
    assert [
        (fact.entity.type, fact.entity.id, fact.field, fact.value, fact.source_ref, fact.source_path)
        for fact in run.facts
    ] == [
        (row.entity.type, row.entity.id, row.field, row.value, row.source.source_ref, row.source.source_path)
        for row in evidence.observations
    ]
    assert run.retrieval_projection == project_retrieval(evidence)
    assert run.history == retrieve_history(run.retrieval_projection.payload)
    assert run.knowledge == retrieve_knowledge(run.retrieval_projection.payload)
    assert run.history.strategy == "channel_bm25_rrf"
    history_replay = retrieve_history(run.retrieval_projection.payload)
    knowledge_replay = retrieve_knowledge(run.retrieval_projection.payload)
    assert run.history == history_replay
    assert run.knowledge == knowledge_replay
    assert history_replay == retrieve_history(run.retrieval_projection.payload)
    assert knowledge_replay == retrieve_knowledge(run.retrieval_projection.payload)
    active_channels = set(run.history.metadata["diagnostics"]["active_modalities"])
    assert active_channels == {
        signal for signal, count in run.retrieval_projection.included_counts.items() if count
    }
    assert len(generator_provider.calls) == len(validator_provider.calls) == 1
    assert run.rca_result.candidate_results[0].evidence_refs == (run.facts[0].fact_id,)
    excluded_ids = {observation_id for observation_id, _ in run.retrieval_projection.excluded_observations}
    excluded_source_refs = {
        observation.source.source_ref
        for observation in evidence.observations
        if observation.observation_id in excluded_ids
    }
    assert excluded_source_refs <= {fact.source_ref for fact in run.facts}
    assert all(item.source_type == "HISTORY" for item in run.history.items)
    assert all(item.source_type == "DOMAIN_KNOWLEDGE" for item in run.knowledge.items)
