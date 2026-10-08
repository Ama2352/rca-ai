"""Offline tests for the supported prepared-demo CLI."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[2]
RUNNER_PATH = PROJECT_ROOT / "scripts" / "run_prepared_demo.py"
_SPEC = importlib.util.spec_from_file_location("run_prepared_demo", RUNNER_PATH)
assert _SPEC is not None and _SPEC.loader is not None
runner = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(runner)


SCENARIOS = (
    "missing-secret-01", "application-failure-01", "ad-high-cpu-01",
    "dependency-unavailable-01", "messaging-failure-01",
)


@pytest.mark.parametrize("scenario", SCENARIOS)
def test_runner_loads_tracked_prepared_fixture(scenario):
    incident = runner.load_incident(scenario)

    assert incident.incident_id == scenario
    assert incident.evidence.observations
    fixture_path = runner.PROJECT_ROOT / runner.SCENARIOS_BY_ID[scenario]["prepared_input"]
    assert fixture_path.is_file()
    assert fixture_path.parent == runner.PROJECT_ROOT / "data" / "demo"
    assert "experiments" not in str(fixture_path)


def test_runner_accepts_one_scenario_or_all_and_pacing_is_opt_in():
    args = runner.build_parser().parse_args([])
    assert args.scenario == "all"
    assert args.enable_pacing is False
    assert args.pacing_delay_seconds == 75

    selected = runner.build_parser().parse_args([
        "--scenario", "ad-high-cpu-01", "--enable-pacing", "--pacing-delay-seconds", "83",
    ])
    assert selected.scenario == "ad-high-cpu-01"
    assert selected.enable_pacing is True
    assert selected.pacing_delay_seconds == 83


def test_runner_wires_groq_generator_and_cerebras_validator_without_default_pacing(monkeypatch):
    calls = {}

    class FakeGroqProvider:
        def __init__(self):
            calls["groq"] = calls.get("groq", 0) + 1

    class FakeCerebrasProvider:
        def __init__(self):
            calls["cerebras"] = calls.get("cerebras", 0) + 1

    class FakePipeline:
        def __init__(self, **kwargs):
            calls["pipeline"] = kwargs

    monkeypatch.setattr(runner, "GroqProvider", FakeGroqProvider)
    monkeypatch.setattr(runner, "CerebrasBenchmarkProvider", FakeCerebrasProvider)
    monkeypatch.setattr(runner, "PreparedDemoPipeline", FakePipeline)

    runner.make_pipeline(enable_pacing=False, pacing_delay_seconds=75)

    assert calls["groq"] == calls["cerebras"] == 1
    assert isinstance(calls["pipeline"]["generator_provider"], FakeGroqProvider)
    assert isinstance(calls["pipeline"]["validator_provider"], FakeCerebrasProvider)
    assert calls["pipeline"]["provider_pacer"] is None


@pytest.mark.parametrize(
    ("arguments", "expected"),
    [
        (["--scenario", "ad-high-cpu-01"], ["ad-high-cpu-01"]),
        ([], list(SCENARIOS)),
    ],
)
def test_runner_main_executes_only_selected_tracked_scenarios(
    arguments, expected, monkeypatch, capsys
):
    executed = []

    class FakePipeline:
        def run(self, incident):
            executed.append(incident.incident_id)
            return incident

    monkeypatch.setenv("GROQ_API_KEY", "offline-test-placeholder")
    monkeypatch.setenv("CEREBRAS_API_KEY", "offline-test-placeholder")
    monkeypatch.setattr(runner, "make_pipeline", lambda **kwargs: FakePipeline())
    monkeypatch.setattr(runner, "summarize_run", lambda run: {"incident_id": run.incident_id})

    assert runner.main(arguments) == 0
    output = json.loads(capsys.readouterr().out)

    assert executed == expected
    assert [item["incident_id"] for item in output["scenarios"]] == expected


@pytest.mark.parametrize("missing_key", ["GROQ_API_KEY", "CEREBRAS_API_KEY"])
def test_runner_stops_before_pipeline_creation_without_credentials(monkeypatch, capsys, missing_key):
    monkeypatch.setenv("GROQ_API_KEY", "offline-test-placeholder")
    monkeypatch.setenv("CEREBRAS_API_KEY", "offline-test-placeholder")
    monkeypatch.delenv(missing_key)
    monkeypatch.setattr(
        runner,
        "make_pipeline",
        lambda **kwargs: pytest.fail("provider pipeline must not be created without a key"),
    )

    assert runner.main(["--scenario", "missing-secret-01"]) == 2
    assert f"{missing_key} is required" in capsys.readouterr().err


def test_runner_enables_one_shared_pacer_only_when_requested(monkeypatch):
    calls = {}

    class FakeGroqProvider:
        pass

    class FakeCerebrasProvider:
        pass

    class FakePacer:
        def __init__(self, *, fallback_delay_seconds):
            calls["delay"] = fallback_delay_seconds

    class FakePipeline:
        def __init__(self, **kwargs):
            calls["pipeline"] = kwargs

    monkeypatch.setattr(runner, "GroqProvider", FakeGroqProvider)
    monkeypatch.setattr(runner, "CerebrasBenchmarkProvider", FakeCerebrasProvider)
    monkeypatch.setattr(runner, "ProviderCallPacer", FakePacer)
    monkeypatch.setattr(runner, "PreparedDemoPipeline", FakePipeline)

    runner.make_pipeline(enable_pacing=True, pacing_delay_seconds=83)

    assert calls["delay"] == 83
    assert calls["pipeline"]["provider_pacer"] is not None


def test_runner_summary_reports_integrity_budget_usage_and_final_result(monkeypatch):
    generation = SimpleNamespace(
        request={"a": "x"},
        provider_result=SimpleNamespace(
            model_returned="openai/gpt-oss-120b",
            usage={"prompt_tokens": 5, "completion_tokens": 2, "total_tokens": 7},
        ),
        hypotheses=(SimpleNamespace(id="HYP1"),),
    )
    validation = SimpleNamespace(
        request={"b": "y"},
        provider_result=SimpleNamespace(
            model_returned="openai/gpt-oss-120b",
            usage={"prompt_tokens": 6, "completion_tokens": 3, "total_tokens": 9},
        ),
        result=SimpleNamespace(
            hypothesis_id="HYP1", decision=SimpleNamespace(value="KEEP_QUALIFIED"),
            support_level=SimpleNamespace(value="PLAUSIBLE"), qualifications=(), unresolved=(),
        ),
    )
    run = SimpleNamespace(
        incident_id="ad-high-cpu-01", facts=(1, 2), fact_integrity=True,
        history=SimpleNamespace(items=(SimpleNamespace(alias="H001"),)),
        knowledge=SimpleNamespace(items=(SimpleNamespace(alias="K001"),)),
        generation=generation, validations=(validation,), rca_result={"candidate_results": []},
    )
    monkeypatch.setattr(runner, "to_dict", lambda value: value)

    summary = runner.summarize_run(run)

    assert summary["fact_integrity"] is True
    assert summary["generator"]["request"] == {"bytes": 9, "estimated_tokens": 3}
    assert summary["validators"][0]["decision"] == "KEEP_QUALIFIED"
    assert summary["token_usage_total"]["total_tokens"] == 16
    assert summary["final_result"] == {"candidate_results": []}
