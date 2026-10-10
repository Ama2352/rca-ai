"""Offline API checks for the prepared-demo UI boundary."""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path

from fastapi.testclient import TestClient
import pytest

from rca_ai.pipeline.orchestrator import RCAPipeline
from rca_ai.providers.contracts import ProviderAttempt, ProviderHTTPError, ProviderResult
from rca_ai.reasoning.validator import ValidatorValidationError
from rca_ai.api import demo
from rca_ai.api.demo import create_app
from rca_ai.demo_catalog import load_scenario_catalog


ROOT = Path(__file__).resolve().parents[3]
SCENARIOS = (
    "missing-secret-01", "application-failure-01", "ad-high-cpu-01",
    "dependency-unavailable-01", "messaging-failure-01", "cart-failure-01",
    "memory-leak-01", "crash-loop-backoff-01", "downstream-latency-01",
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
        pipeline_factory=lambda: RCAPipeline(
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
    assert tuple(row["id"] for row in rows if row["prepared_input"] is not None) == demo.SCENARIOS
    assert len(demo.SCENARIOS) == 9
    assert sum(row["source"] == "otel-demo" for row in rows) == 7
    assert sum(row["source"] == "custom-k8s" for row in rows) == 2
    assert {row["id"] for row in rows if row["readiness"] == "demo-ready"} == {
        "missing-secret-01", "application-failure-01", "ad-high-cpu-01",
        "dependency-unavailable-01", "messaging-failure-01", "cart-failure-01",
        "memory-leak-01",
    }
    assert {row["id"] for row in rows if row["readiness"] == "experimental"} == {
        "crash-loop-backoff-01", "downstream-latency-01",
    }
    for row in rows:
        if row["prepared_input"] is None:
            assert row["prepared_input"] is None
            assert "description" not in row
            continue
        assert row["prepared_input"] == f"data/demo/{row['id']}.json"
        fixture = json.loads((ROOT / "data" / "demo" / f"{row['id']}.json").read_text(encoding="utf-8"))
        signals = {item["signal"] for item in fixture["evidence"]["observations"]}
        assert set(row["available_evidence_sources"]) == signals
        assert not {"title", "description", "symptoms", "affected_services", "investigation_focus", "analysis_mode"}.intersection(row)
        assert "cause" not in row and "observations" not in row and "investigation" not in row


def test_snapshot_ids_and_values_resolve_from_prepared_fixture_and_manifest():
    rows = _client().get("/api/demo/incidents").json()["incidents"]
    manifest = json.loads((ROOT / "data/demo/selection_manifest.json").read_text(encoding="utf-8"))
    for row in rows:
        if row["prepared_input"] is None:
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


def test_overview_snapshot_does_not_select_or_mutate_pipeline_facts():
    from rca_ai.facts.builder import build_fact_view
    from rca_ai.domain.models import to_dict

    rows = {row["id"]: row for row in _client().get("/api/demo/incidents").json()["incidents"]}
    for scenario in SCENARIOS:
        incident = demo.load_incident(scenario)
        before = to_dict(build_fact_view(incident))
        fixture = json.loads((ROOT / "data/demo" / f"{scenario}.json").read_text(encoding="utf-8"))
        assert len(before) == len(fixture["evidence"]["observations"])
        assert len(rows[scenario]["incident_snapshot"]) <= len(before)
        after = to_dict(build_fact_view(demo.load_incident(scenario)))
        assert after == before


def test_overview_snapshot_selection_covers_principal_recorded_symptoms():
    rows = {row["id"]: row for row in _client().get("/api/demo/incidents").json()["incidents"]}
    expected = {
        "missing-secret-01": {"d5563ffafe9100e99220be7f"},
        "application-failure-01": {"823d2b475830b7bac53f7246", "ad56ea564a0349050e79585b"},
        "ad-high-cpu-01": {"310cbe59d2d0675e021d9ef1", "0cad6ea9e3fa4c21136334c4"},
        "dependency-unavailable-01": {"fab7386701318ac5ccbf1dc4"},
        "messaging-failure-01": {"5db48f63cc31148449f4ae55", "0ab116696729eba636058530", "fc473ab2e44e096117841dc2"},
    }
    for scenario, required in expected.items():
        chosen = {item["observation_id"] for item in rows[scenario]["incident_snapshot"]}
        assert required <= chosen
        assert 3 <= len(chosen) <= 6


def test_result_presentation_keeps_exact_fact_value():
    client = _client()
    started = client.post("/api/demo/analyses", json={"incident_id": "application-failure-01"})
    result = _completed(client, started.json()["analysis_id"])
    assert result["status"] == "completed"
    assert len(result["presented_facts"]) == len(result["facts"])
    for fact, shown in zip(result["facts"], result["presented_facts"], strict=True):
        assert shown["id"] == fact["fact_id"]
        assert shown["raw"] == fact


def test_experimental_prepared_scenario_can_be_submitted_and_completed():
    client = _client()
    non_ready = "downstream-latency-01"

    response = client.post("/api/demo/analyses", json={"incident_id": non_ready})

    assert response.status_code == 202
    result = _completed(client, response.json()["analysis_id"])
    assert result["status"] == "completed"
    assert result["incident_id"] == non_ready
    assert result["fact_integrity"] is True


def test_validator_integrity_failure_shows_actual_safe_error_without_result():
    class InvalidValidatorPipeline:
        def run(self, incident, *, observer=None):
            raise ValidatorValidationError("Validator referenced a non-current fact")

    client = TestClient(create_app(
        pipeline_factory=lambda: InvalidValidatorPipeline(), credential_available=lambda: True,
    ))
    started = client.post("/api/demo/analyses", json={"incident_id": "downstream-latency-01"})
    result = _completed(client, started.json()["analysis_id"])

    assert result["status"] == "failed"
    assert result["error"] == {
        "code": "VALIDATION_FAILED",
        "message": "Validator referenced a non-current fact",
    }
    assert "result" not in result


def test_unexpected_analysis_failure_logs_safe_stage_and_exception(caplog, monkeypatch):
    caplog.set_level(logging.ERROR, logger="rca_ai.api.demo")

    def fail_history_load(_path=None):
        raise ValueError("Historical corpus does not match its freeze manifest")

    monkeypatch.setattr("rca_ai.retrieval.history.load_history_store", fail_history_load)
    client = _client()
    started = client.post("/api/demo/analyses", json={"incident_id": "missing-secret-01"})
    result = _completed(client, started.json()["analysis_id"])

    assert result["status"] == "failed"
    assert result["stage"] == "retrieval"
    assert result["error"]["code"] == "ANALYSIS_FAILED"
    records = [record for record in caplog.records if record.name == "rca_ai.api.demo"]
    event = next(json.loads(record.getMessage()) for record in records if '"event": "analysis_failed"' in record.getMessage())
    assert event == {
        "analysis_id": started.json()["analysis_id"],
        "error_message": "Historical corpus does not match its freeze manifest",
        "event": "analysis_failed",
        "exception_type": "ValueError",
        "stage": "retrieval",
    }
    assert not any(secret in json.dumps(event) for secret in ("source_ref", "source_path", "api_key", "token"))


def test_failure_log_omits_untrusted_exception_text(caplog):
    class UnsafeFailurePipeline:
        def run(self, incident, *, observer=None):
            raise RuntimeError("api_key=secret-value raw telemetry payload")

    caplog.set_level(logging.ERROR, logger="rca_ai.api.demo")
    client = TestClient(create_app(
        pipeline_factory=UnsafeFailurePipeline,
        credential_available=lambda: True,
    ))
    started = client.post("/api/demo/analyses", json={"incident_id": "missing-secret-01"})
    result = _completed(client, started.json()["analysis_id"])
    records = [record for record in caplog.records if record.name == "rca_ai.api.demo"]
    event = next(json.loads(record.getMessage()) for record in records if '"event": "analysis_failed"' in record.getMessage())

    assert result["status"] == "failed"
    assert event["exception_type"] == "RuntimeError"
    assert event["error_message"] == "Execution failed; details omitted to protect request and telemetry data"
    assert "secret-value" not in json.dumps(event)
    assert "raw telemetry payload" not in json.dumps(event)


def test_catalog_loader_and_api_share_the_same_scenario_records():
    api_rows = _client().get("/api/demo/incidents").json()["incidents"]
    catalog_rows = load_scenario_catalog()

    assert [row["id"] for row in api_rows] == [row["id"] for row in catalog_rows]


@pytest.mark.parametrize("scenario", SCENARIOS)
def test_prepared_input_endpoint_returns_original_registered_json(scenario):
    response = _client().get(f"/api/demo/incidents/{scenario}/prepared-input")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/json")
    assert response.text == (ROOT / "data" / "demo" / f"{scenario}.json").read_text(encoding="utf-8")
    assert response.json()["incident_id"] == scenario


@pytest.mark.parametrize("scenario", ["unknown", "..", "%2Fetc%2Fpasswd"])
def test_prepared_input_endpoint_rejects_unregistered_scenarios(scenario):
    assert _client().get(f"/api/demo/incidents/{scenario}/prepared-input").status_code == 404


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
        def run(self, incident, *, observer=None):
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
        def run(self, incident, *, observer=None):
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


def test_default_demo_pipeline_wires_groq_and_cerebras_without_extra_provider_wrappers(monkeypatch):
    import rca_ai.api.demo as demo

    class CapturePipeline:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    providers = []
    monkeypatch.setattr(demo, "GroqProvider", lambda: providers.append("groq") or object())
    monkeypatch.setattr(demo, "CerebrasProvider", lambda: providers.append("cerebras") or object())
    monkeypatch.setattr(demo, "RCAPipeline", CapturePipeline)
    pipeline = demo._default_pipeline()

    assert providers == ["groq", "cerebras"]
    assert set(pipeline.kwargs) == {"generator_provider", "validator_provider"}
    assert pipeline.kwargs["generator_provider"] is not pipeline.kwargs["validator_provider"]


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
        def run(self, incident, *, observer=None):
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
        pipeline_factory=lambda: RCAPipeline(
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
