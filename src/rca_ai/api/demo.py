"""Three-route, in-process API over the official RCA pipeline."""

from __future__ import annotations

import json
import os
import time
from copy import deepcopy
from datetime import datetime, timezone
from threading import Lock, Thread
from typing import Callable
from uuid import uuid4

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from rca_ai.demo_catalog import PROJECT_ROOT, SCENARIO_CATALOG, SCENARIOS_BY_ID, runnable_scenario_ids
from rca_ai.api.presentation import present_fact
from rca_ai.domain.models import IncidentInput, canonical_evidence_from_dict, to_dict
from rca_ai.facts.builder import build_fact_view
from rca_ai.pipeline.assembler import resolve_sources
from rca_ai.pipeline.orchestrator import DemoEvent, PipelineRunResult, RCAPipeline
from rca_ai.pipeline.request_budget import RequestBudgetExceeded
from rca_ai.reasoning.generator import GENERATOR_MODEL
from rca_ai.reasoning.validator import ValidatorValidationError
from rca_ai.providers.cerebras import CEREBRAS_MODEL, CerebrasProvider
from rca_ai.providers.contracts import ProviderError, ProviderHTTPError
from rca_ai.providers.groq import GroqProvider


SCENARIOS = runnable_scenario_ids()
_SIGNAL_ORDER = ("metric", "log", "trace", "kubernetes")


def _default_provider_routing() -> dict[str, dict[str, str]]:
    return {
        "generator": {"provider": "Groq", "model": GENERATOR_MODEL},
        "validator": {"provider": "Cerebras", "model": CEREBRAS_MODEL},
    }


def load_incident(scenario: str) -> IncidentInput:
    catalog_row = SCENARIOS_BY_ID.get(scenario)
    if catalog_row is None or catalog_row["prepared_input"] is None:
        raise ValueError("Unsupported prepared scenario")
    fixture_path = PROJECT_ROOT / catalog_row["prepared_input"]
    payload = json.loads(fixture_path.read_text(encoding="utf-8"))
    if payload.get("incident_id") != scenario:
        raise ValueError("Prepared fixture incident ID mismatch")
    return IncidentInput(scenario, canonical_evidence_from_dict(payload["evidence"]))


def incident_catalog() -> list[dict[str, object]]:
    rows = []
    for scenario in SCENARIO_CATALOG:
        item = {
            "id": scenario["id"],
            "source": scenario["source"],
            "readiness": scenario["readiness"],
            "prepared_input": scenario["prepared_input"],
        }
        if scenario["prepared_input"] is not None:
            incident = load_incident(scenario["id"])
            signals = {row.signal for row in incident.evidence.observations}
            facts = build_fact_view(incident)
            snapshot_ids = set(scenario["snapshot_observation_ids"])
            snapshot = [
                {
                    "observation_id": observation.observation_id,
                    "source_ref": observation.source.source_ref,
                    "presentation": to_dict(present_fact(fact)),
                }
                for observation, fact in zip(incident.evidence.observations, facts, strict=True)
                if observation.observation_id in snapshot_ids
            ]
            item.update({
                "available_evidence_sources": [signal for signal in _SIGNAL_ORDER if signal in signals],
                "incident_snapshot": snapshot,
            })
        rows.append(item)
    return rows


def _default_pipeline() -> RCAPipeline:
    generator_provider = GroqProvider()
    validator_provider = CerebrasProvider()
    return RCAPipeline(
        generator_provider=generator_provider, validator_provider=validator_provider,
    )


def _serialize_run(run: PipelineRunResult) -> dict[str, object]:
    return {
        "result": to_dict(run.rca_result),
        "facts": to_dict(run.facts),
        "presented_facts": [to_dict(present_fact(fact)) for fact in run.facts],
        "fact_integrity": run.fact_integrity,
        "resolved_sources_by_candidate": {
            candidate.hypothesis.id: resolve_sources(candidate, run.facts, run.history, run.knowledge)
            for candidate in run.rca_result.candidate_results
        },
        "validations": [to_dict(execution.result) for execution in run.validations],
        "history_ids": [item.alias for item in run.history.items],
        "knowledge_ids": [item.alias for item in run.knowledge.items],
    }


class AnalysisRequest(BaseModel):
    incident_id: str


def create_app(
    *,
    pipeline_factory: Callable[[], RCAPipeline] | None = None,
    credential_available: Callable[[], bool] | None = None,
) -> FastAPI:
    """Own one worker and volatile jobs; no provider is created for catalog reads."""

    app = FastAPI(title="RCA prepared-demo API")
    make_pipeline = pipeline_factory or _default_pipeline
    has_credential = credential_available or (
        lambda: bool(os.getenv("GROQ_API_KEY", "").strip())
        and bool(os.getenv("CEREBRAS_API_KEY", "").strip())
    )
    default_routing = _default_provider_routing() if pipeline_factory is None else None
    jobs: dict[str, dict[str, object]] = {}
    started_clocks: dict[str, float] = {}
    lock = Lock()
    running_id: str | None = None

    @app.get("/api/demo/incidents")
    def list_incidents():
        return {"incidents": incident_catalog()}

    @app.post("/api/demo/analyses", status_code=202)
    def start_analysis(request: AnalysisRequest):
        nonlocal running_id
        if request.incident_id not in SCENARIOS:
            if request.incident_id in SCENARIOS_BY_ID:
                raise HTTPException(status_code=409, detail="Scenario is not available for Demo v1 analysis")
            raise HTTPException(status_code=404, detail="Unknown incident")
        if not has_credential():
            raise HTTPException(status_code=503, detail="RCA provider credentials are unavailable")
        started_clock = time.perf_counter()
        started_at = datetime.now(timezone.utc).isoformat()
        try:
            incident = load_incident(request.incident_id)
        except (OSError, ValueError, KeyError, json.JSONDecodeError) as error:
            raise HTTPException(status_code=503, detail="Prepared incident input is unavailable or invalid") from error
        prepared_seconds = time.perf_counter() - started_clock
        with lock:
            if running_id is not None:
                raise HTTPException(status_code=409, detail="An analysis is already running")
            analysis_id = uuid4().hex
            jobs[analysis_id] = {
                "analysis_id": analysis_id,
                "incident_id": request.incident_id,
                "status": "queued",
                "stage": "preparation",
                "stage_label": "Preparing incident",
                "started_at": started_at,
                "stage_started_at": started_at,
                "completed_stages": [{"stage": "preparation", "seconds": prepared_seconds}],
                "execution_audit": {"total_seconds": None, "rows": [{
                    "name": "preparation", "seconds": prepared_seconds,
                    "relationship": "exclusive",
                }], "routing": default_routing},
            }
            started_clocks[analysis_id] = started_clock
            running_id = analysis_id

        def work():
            nonlocal running_id
            active: dict[str, object] = {}
            stage_labels = {
                "evidence": "Building and verifying evidence",
                "retrieval": "Retrieving historical and domain context",
                "generation": "Generating hypotheses",
                "validation": "Validating hypotheses",
                "assembly": "Assembling result",
            }

            def record(event: DemoEvent) -> None:
                with lock:
                    job = jobs[analysis_id]
                    audit = job["execution_audit"]
                    rows = audit["rows"]
                    if event.kind == "stage_started":
                        active.clear()
                        active.update(start=event.timestamp, provider=0.0)
                        job.update(stage=event.stage, stage_label=stage_labels[event.stage],
                                   candidate_id=event.candidate_id,
                                   stage_started_at=datetime.now(timezone.utc).isoformat())
                    elif event.kind == "provider_started":
                        active[event.kind] = event.timestamp
                    elif event.kind in {"provider_completed", "provider_failed"}:
                        beginning = active.pop("provider_started", None)
                        if isinstance(beginning, (int, float)):
                            seconds = max(0.0, event.timestamp - beginning)
                            active["provider"] = float(active.get("provider", 0.0)) + seconds
                            row = {"name": f"{event.stage}_provider",
                                   "seconds": seconds, "relationship": "exclusive",
                                   "candidate_id": event.candidate_id}
                            for field in ("attempts", "http_429s", "retry_after_seconds"):
                                detail = getattr(event, field)
                                if detail is not None:
                                    row[field] = detail
                            rows.append(row)
                    elif event.kind in {"stage_completed", "stage_failed"}:
                        beginning = active.get("start")
                        if isinstance(beginning, (int, float)):
                            wall = max(0.0, event.timestamp - beginning)
                            local = max(0.0, wall - float(active.get("provider", 0.0)))
                            rows.append({"name": event.stage, "seconds": local,
                                         "relationship": "exclusive", "candidate_id": event.candidate_id,
                                         "status": "partial" if event.kind == "stage_failed" else "completed"})
                            if event.kind == "stage_completed":
                                job["completed_stages"].append({"stage": event.stage,
                                                                 "candidate_id": event.candidate_id, "seconds": wall})

            with lock:
                jobs[analysis_id]["status"] = "running"
            try:
                pipeline = make_pipeline()
                run = pipeline.run(incident, observer=record)
                completed = _serialize_run(run)
                with lock:
                    jobs[analysis_id].update(status="completed", stage="completed", stage_label="Completed",
                                             candidate_id=None, **completed)
            except Exception as error:
                # Raw provider bodies may contain sensitive input. Return a stable category only.
                if isinstance(error, RequestBudgetExceeded):
                    failure = {"code": "BUDGET_EXCEEDED"}
                elif isinstance(error, ProviderHTTPError) and error.status_code == 429:
                    retry_after = next((
                        attempt.retry_after_seconds for attempt in reversed(error.attempt_log)
                        if attempt.http_status == 429 and attempt.retry_after_seconds is not None
                    ), None)
                    failure = {"code": "RATE_LIMITED"}
                    if retry_after is not None:
                        failure["retry_after_seconds"] = retry_after
                elif isinstance(error, ProviderError):
                    failure = {"code": "PROVIDER_FAILED"}
                elif isinstance(error, ValidatorValidationError):
                    failure = {
                        "code": "VALIDATION_FAILED",
                        "message": str(error),
                    }
                else:
                    failure = {"code": "ANALYSIS_FAILED"}
                with lock:
                    jobs[analysis_id].update(status="failed", error=failure)
            finally:
                with lock:
                    jobs[analysis_id]["execution_audit"]["total_seconds"] = time.perf_counter() - started_clocks[analysis_id]
                    running_id = None

        Thread(target=work, name=f"rca-demo-{analysis_id[:8]}", daemon=True).start()
        return {"analysis_id": analysis_id, "incident_id": request.incident_id, "status": "queued"}

    @app.get("/api/demo/analyses/{analysis_id}")
    def get_analysis(analysis_id: str):
        with lock:
            job = jobs.get(analysis_id)
            if job is None:
                raise HTTPException(status_code=404, detail="Unknown analysis")
            result = deepcopy(job)
            result["elapsed_seconds"] = (
                job["execution_audit"]["total_seconds"]
                if job["status"] in {"completed", "failed"}
                else time.perf_counter() - started_clocks[analysis_id]
            )
            return result

    return app


app = create_app()
