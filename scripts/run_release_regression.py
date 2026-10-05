"""Run the frozen three-scenario live-provider release regression.

This script only loads frozen inputs, wires the production components, and
persists their returned audit data. Semantic decisions remain inside the
frozen Generator, Validator, and deterministic assembler.
"""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sys
from typing import Any

from rca_ai.domain.models import IncidentInput, to_dict
from rca_ai.facts.builder import build_fact_view, verify_fact_view
from rca_ai.facts.selector import request_bytes, select_facts
from rca_ai.pipeline.assembler import assemble_result, resolve_sources
from rca_ai.pipeline.orchestrator import RCAPipeline
from rca_ai.providers.groq import GroqProvider
from rca_ai.reasoning.generator import (
    GENERATOR_MAX_COMPLETION_TOKENS,
    GENERATOR_MODEL,
    GENERATOR_REASONING_EFFORT,
    GENERATOR_TEMPERATURE,
    HypothesisGenerator,
    build_generator_request,
)
from rca_ai.reasoning.prompts import GENERATOR_SYSTEM_PROMPT, VALIDATOR_SYSTEM_PROMPT
from rca_ai.reasoning.schemas import GENERATOR_JSON_SCHEMA, VALIDATOR_JSON_SCHEMA
from rca_ai.reasoning.validator import HypothesisValidator
from rca_ai.retrieval.history import retrieve_history
from rca_ai.retrieval.knowledge import retrieve_knowledge


PROJECT_ROOT = Path(__file__).resolve().parents[1]
FIXTURE_ROOT = PROJECT_ROOT / "tests" / "fixtures"
SCENARIOS = (
    "missing-secret-01",
    "application-failure-01",
    "ad-high-cpu-01",
)
RETRIEVAL_INPUTS = {
    "missing-secret-01": FIXTURE_ROOT / "retrieval" / "inputs" / "channel-incident-01.json",
    "application-failure-01": FIXTURE_ROOT / "retrieval" / "inputs" / "channel-incident-02.json",
    "ad-high-cpu-01": FIXTURE_ROOT / "retrieval" / "inputs" / "plain-query.txt",
}
EXPECTED_COUNTS = {
    "missing-secret-01": (21, 21, 3, 3),
    "application-failure-01": (52, 25, 3, 1),
    "ad-high-cpu-01": (14, 14, 3, 2),
}
FROZEN_HASHES = {
    "generator_prompt": "2902e2200777ea4731cd0baaf9cff616e9ee637c0a1344202fbc9d32607c98de",
    "generator_schema": "26df3bd25892a50bdad1859b31d1a3fe1dd35fdf92f15fce9954d25abcc10119",
    "validator_prompt": "1b61f29d658c079b27b18ca0d0ea3e59b96e3989f21eef0368d9a1d17c86e6b6",
    "validator_schema": "3fc8c2fe12d2748fc934cfe3ae0bd50ca0db1a13891d71df7922d1e6daeebc06",
}


def frozen_contract_hashes() -> dict[str, str]:
    """Hash frozen prompts and schemas using the migration regression method."""
    return {
        "generator_prompt": hashlib.sha256(GENERATOR_SYSTEM_PROMPT.encode("utf-8")).hexdigest(),
        "generator_schema": hashlib.sha256(
            json.dumps(GENERATOR_JSON_SCHEMA, sort_keys=True).encode("utf-8")
        ).hexdigest(),
        "validator_prompt": hashlib.sha256(VALIDATOR_SYSTEM_PROMPT.encode("utf-8")).hexdigest(),
        "validator_schema": hashlib.sha256(
            json.dumps(VALIDATOR_JSON_SCHEMA, sort_keys=True).encode("utf-8")
        ).hexdigest(),
    }


def audit_secret_leak(directory: Path, secret: str) -> bool:
    """Return whether any persisted artifact contains the exact credential."""
    if not secret:
        return False
    needle = secret.encode("utf-8")
    return any(needle in path.read_bytes() for path in directory.rglob("*") if path.is_file())


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _load_incident(scenario: str) -> IncidentInput:
    normalized = _read_json(FIXTURE_ROOT / "facts" / "inputs" / f"{scenario}.normalized.json")
    query_path = RETRIEVAL_INPUTS[scenario]
    retrieval_input = (
        query_path.read_text(encoding="utf-8")
        if query_path.suffix == ".txt"
        else _read_json(query_path)
    )
    return IncidentInput(scenario, normalized, retrieval_input)


def _preflight(incident: IncidentInput) -> dict[str, Any]:
    """Check frozen deterministic counts and request configuration before any live call."""
    facts = build_fact_view(incident)
    if not verify_fact_view(facts, incident):
        raise RuntimeError(f"Fact integrity failed for {incident.incident_id}")
    history = retrieve_history(incident.retrieval_input)
    knowledge = retrieve_knowledge(incident.retrieval_input)
    size_for = lambda candidate: request_bytes(build_generator_request(candidate, history, knowledge))
    selection = select_facts(facts, request_size_for=size_for)
    request = build_generator_request(selection.facts, history, knowledge)
    if (
        request["model"] != GENERATOR_MODEL
        or request["reasoning_effort"] != GENERATOR_REASONING_EFFORT
        or request["temperature"] != GENERATOR_TEMPERATURE
        or request["max_completion_tokens"] != GENERATOR_MAX_COMPLETION_TOKENS
        or request["response_format"]["json_schema"]["strict"] is not True
    ):
        raise RuntimeError("Generator request configuration differs from the frozen contract")
    actual = (len(facts), selection.selected_fact_count, len(history.items), len(knowledge.items))
    if actual != EXPECTED_COUNTS[incident.incident_id]:
        raise RuntimeError(
            f"Deterministic pre-LLM counts changed for {incident.incident_id}: {actual}"
        )
    return {
        "fact_ids": [fact.fact_id for fact in facts],
        "selected_ids": list(selection.selected_ids),
        "full_request_bytes": selection.full_request_bytes,
        "selected_request_bytes": selection.selected_request_bytes,
        "history_ids": [item.alias for item in history.items],
        "knowledge_ids": [item.alias for item in knowledge.items],
    }


def _provider_metadata(result) -> dict[str, Any]:
    return {
        "http_status": result.http_status,
        "attempts": result.attempts,
        "response_id": result.response_id,
        "model_returned": result.model_returned,
        "finish_reason": result.finish_reason,
        "usage": to_dict(result.usage),
        "latency_seconds": result.latency_seconds,
        "rate_limit_headers": to_dict(result.rate_limit_headers),
        "attempt_log": to_dict(result.attempt_log),
    }


def _save_success(folder: Path, run, preflight: dict[str, Any]) -> dict[str, Any]:
    """Persist the actual returned stages and verify output provenance/reassembly."""
    _write_json(folder / "fact_view.json", to_dict(run.facts))
    _write_json(folder / "fact_selection.json", {
        "selected_facts": to_dict(run.selection.facts),
        "selected_ids": list(run.selection.selected_ids),
        "omitted_ids": list(run.selection.omitted_ids),
        "selection_reasons": dict(run.selection.selection_reasons),
        "selector_used": run.selection.selector_used,
        "full_fact_count": run.selection.full_fact_count,
        "selected_fact_count": run.selection.selected_fact_count,
        "full_request_bytes": run.selection.full_request_bytes,
        "selected_request_bytes": run.selection.selected_request_bytes,
        "selected_fact_bytes": run.selection.selected_fact_bytes,
    })
    _write_json(folder / "history_retrieval.json", to_dict(run.history))
    _write_json(folder / "knowledge_retrieval.json", to_dict(run.knowledge))
    _write_json(folder / "generator_request.json", run.generation.request)
    _write_json(folder / "generator_response.json", {
        "content": run.generation.provider_result.content,
        "raw_content": run.generation.provider_result.raw_content,
        "provider": _provider_metadata(run.generation.provider_result),
    })

    for execution in run.validations:
        candidate_folder = folder / "validator" / execution.result.hypothesis_id
        _write_json(candidate_folder / "request.json", execution.request)
        _write_json(candidate_folder / "response.json", {
            "content": execution.provider_result.content,
            "raw_content": execution.provider_result.raw_content,
            "provider": _provider_metadata(execution.provider_result),
        })

    final_result = to_dict(run.rca_result)
    _write_json(folder / "final_result.json", final_result)
    resolved = [
        resolve_sources(candidate, run.selection.facts, run.history, run.knowledge)
        for candidate in run.rca_result.candidate_results
    ]
    _write_json(folder / "resolved_sources.json", resolved)

    reassembled = assemble_result(
        run.incident_id,
        run.generation.hypotheses,
        tuple(execution.result for execution in run.validations),
        run.selection.facts,
        run.history,
        run.knowledge,
    )
    reassembly_pass = to_dict(reassembled) == final_result

    f_ids = {fact.fact_id for fact in run.selection.facts}
    h_ids = {item.alias for item in run.history.items}
    k_ids = {item.alias for item in run.knowledge.items}
    provenance_pass = all(
        set(candidate.evidence_refs) <= f_ids
        and set(candidate.history_refs) <= h_ids
        and set(candidate.knowledge_refs) <= k_ids
        for candidate in run.rca_result.candidate_results
    )
    expected_retained = [
        hypothesis.id for hypothesis, execution in zip(
            run.generation.hypotheses, run.validations, strict=True
        ) if execution.result.decision.value != "REJECT"
    ]
    order_pass = [row.hypothesis.id for row in run.rca_result.candidate_results] == expected_retained

    providers = [run.generation.provider_result, *(item.provider_result for item in run.validations)]
    usage = {
        token: sum(int(item.usage.get(token, 0) or 0) for item in providers)
        for token in ("prompt_tokens", "completion_tokens", "total_tokens")
    }
    summary = {
        "incident_id": run.incident_id,
        "status": "COMPLETED",
        "facts": len(run.facts),
        "selected_facts": run.selection.selected_fact_count,
        "history_count": len(run.history.items),
        "knowledge_count": len(run.knowledge.items),
        "generated_hypotheses": len(run.generation.hypotheses),
        "validator_calls": len(run.validations),
        "retained_candidates": len(run.rca_result.candidate_results),
        "decisions": [execution.result.decision.value for execution in run.validations],
        "support_levels": [execution.result.support_level.value for execution in run.validations],
        "semantic_completions": len(providers),
        "transport_attempts": sum(item.attempts for item in providers),
        "transport_retries": sum(max(0, item.attempts - 1) for item in providers),
        "token_usage": usage,
        "generator_finish_reason": run.generation.provider_result.finish_reason,
        "validator_finish_reasons": [item.provider_result.finish_reason for item in run.validations],
        "deterministic_reassembly": reassembly_pass,
        "provenance_checks": provenance_pass,
        "candidate_order_check": order_pass,
        "preflight": preflight,
    }
    _write_json(folder / "run_summary.json", summary)
    if not (reassembly_pass and provenance_pass and order_pass):
        raise RuntimeError(f"Post-run deterministic/provenance check failed for {run.incident_id}")
    return summary


def main() -> int:
    key = os.getenv("GROQ_API_KEY", "").strip()
    if not key:
        print("GROQ_API_KEY is unavailable; no provider call was attempted.", file=sys.stderr)
        return 2

    hashes = frozen_contract_hashes()
    if hashes != FROZEN_HASHES:
        print("Frozen prompt/schema hash mismatch; no provider call was attempted.", file=sys.stderr)
        return 3

    incidents = [_load_incident(scenario) for scenario in SCENARIOS]
    try:
        preflights = {incident.incident_id: _preflight(incident) for incident in incidents}
    except Exception as exc:
        print(f"Deterministic preflight failed ({type(exc).__name__}); no provider call was attempted.", file=sys.stderr)
        return 4

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    output_root = PROJECT_ROOT / "artifacts" / f"release_regression_{stamp}"
    output_root.mkdir(parents=True, exist_ok=False)
    summary: dict[str, Any] = {
        "timestamp_utc": stamp,
        "artifact_directory": str(output_root),
        "frozen_contract_hashes": hashes,
        "scenarios": {},
        "status": "IN_PROGRESS",
    }

    provider = GroqProvider()
    for incident in incidents:
        folder = output_root / incident.incident_id
        folder.mkdir()
        try:
            pipeline = RCAPipeline(
                generator=HypothesisGenerator(provider),
                validator=HypothesisValidator(provider),
            )
            run = pipeline.run(incident)
            scenario_summary = _save_success(folder, run, preflights[incident.incident_id])
            summary["scenarios"][incident.incident_id] = scenario_summary
            secret_leaked = audit_secret_leak(output_root, key)
            scenario_summary["secret_leak_audit"] = not secret_leaked
            _write_json(folder / "run_summary.json", scenario_summary)
            if secret_leaked:
                summary["status"] = "FAILED_SECRET_LEAK_AUDIT"
                break
        except Exception as exc:
            summary["scenarios"][incident.incident_id] = {
                "status": "EXECUTION_OR_CONTRACT_FAILURE",
                "error_type": type(exc).__name__,
                "provider_attempts": getattr(exc, "attempts", None),
                "http_status": getattr(exc, "status_code", None),
            }
            summary["status"] = "FAILED"
            break

    if summary["status"] == "IN_PROGRESS":
        summary["status"] = "PASS"
    summary["secret_leak_audit"] = not audit_secret_leak(output_root, key)
    summary["classification"] = (
        "RCA_CLEAN_REBUILD_RELEASE_PASS"
        if summary["status"] == "PASS" and summary["secret_leak_audit"]
        else "RCA_CLEAN_REBUILD_RELEASE_FAIL"
    )
    _write_json(output_root / "summary.json", summary)
    print(f"Artifacts: {output_root}")
    print(f"Classification: {summary['classification']}")
    return 0 if summary["classification"] == "RCA_CLEAN_REBUILD_RELEASE_PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
