"""Run RCA Demo v1 on one or all tracked prepared incident fixtures."""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any

from rca_ai.domain.models import IncidentInput, canonical_evidence_from_dict, to_dict
from rca_ai.demo_catalog import PROJECT_ROOT, SCENARIOS_BY_ID, runnable_scenario_ids
from rca_ai.pipeline.orchestrator import RCAPipeline
from rca_ai.pipeline.request_budget import DEFAULT_MAX_ESTIMATED_TOKENS, request_size
from rca_ai.providers.groq import GroqProvider
from rca_ai.providers.cerebras import CerebrasProvider


SCENARIOS = runnable_scenario_ids()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run RCA on the reviewed prepared incident inputs without the telemetry Processor."
    )
    parser.add_argument(
        "--scenario",
        choices=(*SCENARIOS, "all"),
        default="all",
        help="prepared incident to run (default: all, sequentially)",
    )
    parser.add_argument(
        "--max-estimated-tokens",
        type=int,
        default=DEFAULT_MAX_ESTIMATED_TOKENS,
        help="complete request guard using ceil(UTF-8 bytes / 4) (default: 7000)",
    )
    return parser


def load_incident(scenario: str) -> IncidentInput:
    """Load a version-controlled prepared fixture; never consult experiment artifacts."""

    catalog_row = SCENARIOS_BY_ID.get(scenario)
    if catalog_row is None or catalog_row["prepared_input"] is None:
        raise ValueError(f"Unsupported scenario: {scenario}")
    fixture_path = PROJECT_ROOT / catalog_row["prepared_input"]
    payload = json.loads(fixture_path.read_text(encoding="utf-8"))
    if payload.get("incident_id") != scenario:
        raise ValueError(f"Fixture incident_id does not match selected scenario: {scenario}")
    return IncidentInput(
        scenario,
        canonical_evidence_from_dict(payload["evidence"]),
    )


def make_pipeline(
    *,
    max_estimated_tokens: int = DEFAULT_MAX_ESTIMATED_TOKENS,
) -> RCAPipeline:
    """Build the official RCA pipeline with the configured providers."""

    generator_provider = GroqProvider()
    validator_provider = CerebrasProvider()
    return RCAPipeline(
        generator_provider=generator_provider,
        validator_provider=validator_provider,
        max_estimated_tokens=max_estimated_tokens,
    )


def _request_metrics(request: dict[str, Any]) -> dict[str, int]:
    request_bytes, estimated_tokens = request_size(request)
    return {"bytes": request_bytes, "estimated_tokens": estimated_tokens}


def summarize_run(run: Any) -> dict[str, Any]:
    """Return compact operational metadata and the deterministically assembled result."""

    generation = run.generation
    generator_provider = generation.provider_result
    validators = []
    provider_results = [generator_provider]
    for execution in run.validations:
        result = execution.result
        provider_result = execution.provider_result
        provider_results.append(provider_result)
        validators.append({
            "hypothesis_id": result.hypothesis_id,
            "decision": result.decision.value,
            "support_level": result.support_level.value,
            "qualifications": to_dict(result.qualifications),
            "unresolved": to_dict(result.unresolved),
            "model": provider_result.model_returned,
            "usage": to_dict(provider_result.usage),
            "request": _request_metrics(execution.request),
        })

    token_keys = ("prompt_tokens", "completion_tokens", "total_tokens")
    return {
        "incident_id": run.incident_id,
        "fact_integrity": run.fact_integrity,
        "fact_count": len(run.facts),
        "history_ids": [item.alias for item in run.history.items],
        "knowledge_ids": [item.alias for item in run.knowledge.items],
        "generator": {
            "model": generator_provider.model_returned,
            "usage": to_dict(generator_provider.usage),
            "request": _request_metrics(generation.request),
            "hypothesis_ids": [hypothesis.id for hypothesis in generation.hypotheses],
        },
        "validators": validators,
        "token_usage_total": {
            key: sum(int(provider.usage.get(key, 0) or 0) for provider in provider_results)
            for key in token_keys
        },
        "final_result": to_dict(run.rca_result),
    }


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    missing_credentials = [
        name for name in ("GROQ_API_KEY", "CEREBRAS_API_KEY")
        if not os.getenv(name, "").strip()
    ]
    if missing_credentials:
        print(f"{', '.join(missing_credentials)} is required; no provider request was made.", file=sys.stderr)
        return 2

    scenarios = SCENARIOS if args.scenario == "all" else (args.scenario,)
    pipeline = make_pipeline(max_estimated_tokens=args.max_estimated_tokens)
    output: list[dict[str, Any]] = []
    for scenario in scenarios:
        try:
            output.append(summarize_run(pipeline.run(load_incident(scenario))))
        except Exception as error:
            failure = {
                "status": "FAIL",
                "scenario": scenario,
                "error_type": type(error).__name__,
                "http_status": getattr(error, "status_code", None),
                "message": str(error),
                "completed_scenarios": output,
            }
            print(json.dumps(failure, ensure_ascii=False, indent=2), file=sys.stderr)
            return 1

    print(json.dumps({"status": "COMPLETE", "scenarios": output}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
