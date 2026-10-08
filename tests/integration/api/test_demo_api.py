"""Offline API checks for the prepared-demo UI boundary."""

from __future__ import annotations

import json
import time
from pathlib import Path

from fastapi.testclient import TestClient
import pytest

from rca_ai.pipeline.prepared_demo import PreparedDemoPipeline
from rca_ai.providers.groq import ProviderAttempt, ProviderHTTPError, ProviderResult
from rca_ai.api.demo import create_app
from rca_ai.demo_catalog import load_scenario_catalog


ROOT = Path(__file__).resolve().parents[3]
SCENARIOS = (
    "missing-secret-01", "application-failure-01", "ad-high-cpu-01",
    "dependency-unavailable-01", "messaging-failure-01",
)


def _response(content):
    return ProviderResult(
        content=content, raw_content=json.dumps(content), http_status=200, attempts=1,
        response_id="offline", model_returned="offline", finish_reason="stop",
        usage={}, latency_seconds=0, rate_limit_headers={}, attempt_log=(),
    )


class FakeGenerator:
    def complete(self, request):
        payload = json.loads(request["messages"][1]["content"])
        return _response({"hypotheses": [{
            "id": "HYP1", "explanation": "A qualified explanation.",
            "explains_fact_refs": [payload["current_facts"][0]["fact_id"]],
            "supporting_fact_refs": [payload["current_facts"][0]["fact_id"]],
            "history_refs": [payload["history"][0]["alias"]],
            "knowledge_refs": [payload["domain_knowledge"][0]["alias"]],
            "assumptions": ["Causation is unverified"], "unresolved": ["Confirm mechanism"],
        }]})


class FakeValidator:
    def complete(self, request):
        payload = json.loads(request["messages"][1]["content"])
        fact_id = payload["current_facts"][0]["fact_id"]
        return _response({
            "hypothesis_id": "HYP1", "decision": "KEEP_QUALIFIED",
            "support_level": "PLAUSIBLE", "incident_basis": {"evidence": [fact_id]},
            "hard_violations": [],
            "qualifications": [{"claim": "a cause", "issue": "not established",
                                "fact_refs": [fact_id], "observed_form": "an observation"}],
            "relation_assessment": {"relation": "may explain", "support_level": "PLAUSIBLE",
                                    "fact_refs": [fact_id], "reason": "uncertain"},
            "unresolved": ["Confirm mechanism"],
        })


def _client():
    return TestClient(create_app(
        pipeline_factory=lambda: PreparedDemoPipeline(
            generator_provider=FakeGenerator(), validator_provider=FakeValidator(),
        ),
        credential_available=lambda: True,
    ))


def _completed(client, analysis_id):
    for _ in range(100):
        response = client.get(f"/api/demo/analyses/{analysis_id}")
        assert response.status_code == 200
        if response.json()["status"] in ("completed", "failed"):
            return response.json()
        time.sleep(0.01)
    pytest.fail("offline job did not complete")


def test_catalog_metadata_matches_prepared_observations_without_diagnosis():
    response = _client().get("/api/demo/incidents")
    assert response.status_code == 200
    rows = response.json()["incidents"]
    assert len(rows) == 9
    assert sum(row["source"] == "otel-demo" for row in rows) == 7
    assert sum(row["source"] == "custom-k8s" for row in rows) == 2
    assert {row["id"] for row in rows if row["readiness"] == "demo-ready"} == set(SCENARIOS)
    for row in rows:
        if row["readiness"] != "demo-ready":
            assert row["prepared_input"] is None
            assert "description" not in row
            continue
        assert row["prepared_input"] == f"data/demo/{row['id']}.json"
        fixture = json.loads((ROOT / "data" / "demo" / f"{row['id']}.json").read_text(encoding="utf-8"))
        signals = {item["signal"] for item in fixture["evidence"]["observations"]}
        assert set(row["available_evidence_sources"]) == signals
        assert row["title"] and row["description"] and row["symptoms"]
        assert row["affected_services"] and len(row["investigation_focus"]) in (2, 3)
        assert all(service in json.dumps(fixture["evidence"]) for service in row["affected_services"])
        assert "eda-capture-secret-does-not-exist" not in json.dumps(row)
        assert "root cause" not in row["description"].lower()


def test_snapshot_ids_and_values_resolve_from_prepared_fixture_and_manifest():
    rows = _client().get("/api/demo/incidents").json()["incidents"]
    manifest = json.loads((ROOT / "data/demo/selection_manifest.json").read_text(encoding="utf-8"))
    for row in rows:
        if row["readiness"] != "demo-ready":
            assert "incident_snapshot" not in row
            continue
        fixture = json.loads((ROOT / row["prepared_input"]).read_text(encoding="utf-8"))
        observations = {item["observation_id"]: item for item in fixture["evidence"]["observations"]}
        included = {item["observation_id"]: item for item in manifest["scenarios"][row["id"]]["included_observations"]}
        assert row["incident_snapshot"]
        for entry in row["incident_snapshot"]:
            original = observations[entry["observation_id"]]
            audit = included[entry["observation_id"]]
            assert entry["source_ref"] == original["source"]["source_ref"] == audit["source_ref"]
            assert entry["presentation"]["raw"]["value"] == original["value"]
            assert entry["presentation"]["signal_type"] == original["signal"]
        assert "snapshot_observation_ids" not in row


def test_result_presentation_keeps_exact_fact_value():
    client = _client()
    started = client.post("/api/demo/analyses", json={"incident_id": "application-failure-01"})
    result = _completed(client, started.json()["analysis_id"])
    assert result["status"] == "completed"
    assert len(result["presented_facts"]) == len(result["facts"])
    for fact, shown in zip(result["facts"], result["presented_facts"], strict=True):
        assert shown["id"] == fact["fact_id"]
        assert shown["raw"] == fact


def test_catalog_prevents_experimental_scenarios_from_running():
    client = _client()
    rows = client.get("/api/demo/incidents").json()["incidents"]
    experimental = next(row["id"] for row in rows if row["readiness"] == "experimental")

    response = client.post("/api/demo/analyses", json={"incident_id": experimental})

    assert response.status_code == 409
    assert "not available for Demo v1" in response.json()["detail"]


def test_catalog_loader_and_api_share_the_same_scenario_records():
    api_rows = _client().get("/api/demo/incidents").json()["incidents"]
    catalog_rows = load_scenario_catalog()

    assert [row["id"] for row in api_rows] == [row["id"] for row in catalog_rows]


@pytest.mark.parametrize("scenario", SCENARIOS)
def test_analysis_returns_real_candidate_specific_sources_and_qualifications(scenario):
    client = _client()
    started = client.post("/api/demo/analyses", json={"incident_id": scenario})
    assert started.status_code == 202
    result = _completed(client, started.json()["analysis_id"])
    assert result["status"] == "completed"
    assert result["incident_id"] == scenario
    candidate = result["result"]["candidate_results"][0]
    assert candidate["analysis"]["decision"] == "KEEP_QUALIFIED"
    assert candidate["qualifications"][0]["issue"] == "not established"
    assert candidate["evidence_refs"] == ["F1"]
    sources = result["resolved_sources_by_candidate"]["HYP1"]
    assert sources["evidence"][0]["fact_id"] == "F1"
    assert sources["evidence"][0]["source_ref"] == result["facts"][0]["source_ref"]
    assert sources["history"][0]["alias"].startswith("H")
    assert sources["domain_knowledge"][0]["alias"].startswith("K")
    assert result["fact_integrity"] is True


def test_invalid_scenario_and_missing_credentials_never_start_provider_work():
    client = TestClient(create_app(credential_available=lambda: False))
    assert client.post("/api/demo/analyses", json={"incident_id": "other"}).status_code == 404
    assert client.post("/api/demo/analyses", json={"incident_id": SCENARIOS[0]}).status_code == 503
    assert client.get("/api/demo/analyses/unknown").status_code == 404


def test_concurrent_submission_is_rejected_and_failure_is_separate_from_abstention():
    from threading import Event

    gate = Event()

    class FailingPipeline:
        def run(self, incident):
            gate.wait(2)
            raise RuntimeError("provider unavailable")

    client = TestClient(create_app(
        pipeline_factory=lambda: FailingPipeline(), credential_available=lambda: True,
    ))
    first = client.post("/api/demo/analyses", json={"incident_id": SCENARIOS[0]})
    assert first.status_code == 202
    assert client.post("/api/demo/analyses", json={"incident_id": SCENARIOS[1]}).status_code == 409
    gate.set()
    result = _completed(client, first.json()["analysis_id"])
    assert result["status"] == "failed"
    assert result["error"]["code"] == "ANALYSIS_FAILED"
    assert "result" not in result


def test_exhausted_provider_429_returns_sanitized_rate_limit_and_retry_after():
    class RateLimitedPipeline:
        def run(self, incident):
            raise ProviderHTTPError(
                "provider request failed", attempts=3, status_code=429,
                response_detail='{"error":"too many requests"}',
                attempt_log=(
                    ProviderAttempt(1, http_status=429, retry_after_seconds=12.5),
                    ProviderAttempt(2, http_status=429, retry_after_seconds=12.5),
                    ProviderAttempt(3, http_status=429, retry_after_seconds=12.5),
                ),
            )

    client = TestClient(create_app(
        pipeline_factory=lambda: RateLimitedPipeline(), credential_available=lambda: True,
    ))
    started = client.post("/api/demo/analyses", json={"incident_id": SCENARIOS[0]})
    result = _completed(client, started.json()["analysis_id"])

    assert result["status"] == "failed"
    assert result["error"] == {"code": "RATE_LIMITED", "retry_after_seconds": 12.5}
    assert "response_detail" not in result["error"]


def test_default_demo_pipeline_does_not_enable_proactive_pacing(monkeypatch):
    import rca_ai.api.demo as demo

    class CapturePipeline:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    providers = []
    monkeypatch.setenv("RCA_DEMO_ENABLE_PACING", "1")
    monkeypatch.setattr(demo, "GroqProvider", lambda: providers.append("groq") or object())
    monkeypatch.setattr(demo, "CerebrasBenchmarkProvider", lambda: providers.append("cerebras") or object())
    monkeypatch.setattr(demo, "PreparedDemoPipeline", CapturePipeline)
    pipeline = demo._default_pipeline()

    assert providers == ["groq", "cerebras"]
    assert pipeline.kwargs["generator_provider"] is not pipeline.kwargs["validator_provider"]
    assert "provider_pacer" not in pipeline.kwargs


def test_default_provider_routing_is_explicit_in_completed_execution_audit():
    from rca_ai.api.demo import _default_provider_routing

    assert _default_provider_routing() == {
        "generator": {"provider": "Groq", "model": "openai/gpt-oss-120b"},
        "validator": {"provider": "Cerebras", "model": "gpt-oss-120b"},
    }


def test_default_api_requires_both_provider_credentials(monkeypatch):
    for name in ("GROQ_API_KEY", "CEREBRAS_API_KEY"):
        monkeypatch.setenv(name, "offline-placeholder")
    client = TestClient(create_app())

    for missing in ("GROQ_API_KEY", "CEREBRAS_API_KEY"):
        monkeypatch.delenv(missing)
        response = client.post("/api/demo/analyses", json={"incident_id": SCENARIOS[0]})
        assert response.status_code == 503
        monkeypatch.setenv(missing, "offline-placeholder")


def test_default_job_exposes_actual_provider_routing_without_live_calls(monkeypatch):
    import rca_ai.api.demo as demo

    class OfflineFailurePipeline:
        def run(self, incident):
            raise RuntimeError("offline routing audit test")

    monkeypatch.setattr(demo, "_default_pipeline", OfflineFailurePipeline)
    client = TestClient(create_app(credential_available=lambda: True))
    started = client.post("/api/demo/analyses", json={"incident_id": SCENARIOS[0]})
    result = _completed(client, started.json()["analysis_id"])

    assert result["execution_audit"]["routing"] == demo._default_provider_routing()


def test_job_exposes_real_stage_progress_and_authoritative_timing():
    from threading import Event

    entered = Event()
    release = Event()

    class WaitingGenerator(FakeGenerator):
        def complete(self, request):
            entered.set()
            assert release.wait(3)
            return super().complete(request)

    client = TestClient(create_app(
        pipeline_factory=lambda: PreparedDemoPipeline(
            generator_provider=WaitingGenerator(), validator_provider=FakeValidator(),
        ), credential_available=lambda: True,
    ))
    started = client.post("/api/demo/analyses", json={"incident_id": "missing-secret-01"})
    assert started.status_code == 202
    assert entered.wait(3)
    running = client.get(f"/api/demo/analyses/{started.json()['analysis_id']}").json()
    assert running["stage"] == "generation"
    assert [item["stage"] for item in running["completed_stages"]] == ["preparation", "evidence", "retrieval"]
    assert running["elapsed_seconds"] >= 0
    release.set()
    final = _completed(client, started.json()["analysis_id"])
    assert final["status"] == "completed"
    audit = final["execution_audit"]
    assert audit["total_seconds"] >= 0
    names = [item["name"] for item in audit["rows"]]
    assert {"preparation", "evidence", "retrieval", "generation_provider", "validation_provider", "assembly"} <= set(names)
    assert all(item["relationship"] == "exclusive" for item in audit["rows"])
    assert sum(item["seconds"] for item in audit["rows"]) <= audit["total_seconds"] + 0.02
