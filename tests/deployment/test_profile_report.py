from __future__ import annotations

import importlib.util
from pathlib import Path


MODULE_PATH = Path(__file__).parents[2] / "scripts" / "profile_production.py"
spec = importlib.util.spec_from_file_location("profile_production", MODULE_PATH)
profile = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(profile)


def test_profile_refuses_real_keys(monkeypatch, capsys):
    monkeypatch.setenv("GROQ_API_KEY", "never-print-this")
    monkeypatch.delenv("CEREBRAS_API_KEY", raising=False)

    def docker_must_not_run(*args, **kwargs):
        raise AssertionError("Docker must not run when provider credentials are present")

    monkeypatch.setattr(profile, "_docker", docker_must_not_run)
    assert profile.main([]) == 2
    output = capsys.readouterr()
    assert "Refusing to profile" in output.err
    assert "never-print-this" not in output.err
    assert profile.provider_keys_present({"GROQ_API_KEY": "not-a-real-value"})
    assert not profile.provider_keys_present({"GROQ_API_KEY": "", "CEREBRAS_API_KEY": ""})


def test_report_contains_three_trials_and_peak():
    trials = [
        {"trial": n, "peak_memory_bytes": n * 100, "peak_cpu_percent": n * 10,
         "stats_samples": [f"{n * 100}B / 1GiB|{n * 10}%"],
         "scenarios_completed": profile.SCENARIO_IDS}
        for n in range(1, 4)
    ]
    assert profile.parse_docker_stats_output("300B / 1GiB|30.0%") == (300, 30.0)
    report = profile.build_report(trials, image_sizes={}, disk={})
    assert len(report["trials"]) == 3
    assert report["peaks"] == {"memory_bytes": 300, "cpu_percent": 30}


def test_all_nine_scenarios_are_exercised_offline():
    trials = [
        {"trial": n, "peak_memory_bytes": 1, "peak_cpu_percent": 1,
         "stats_samples": ["1MiB / 1GiB|1%"],
         "scenarios_completed": profile.SCENARIO_IDS}
        for n in range(1, 4)
    ]
    report = profile.build_report(trials, image_sizes={}, disk={})
    assert report["scenario_coverage"] == list(profile.SCENARIO_IDS)
    trials[0]["scenarios_completed"] = profile.SCENARIO_IDS[:-1]
    try:
        profile.build_report(trials, image_sizes={}, disk={})
    except ValueError as error:
        assert "coverage" in str(error).lower()
    else:
        raise AssertionError("incomplete scenario coverage must be rejected")


def test_exercise_submits_and_polls_every_scenario():
    calls = []

    def fake_request(url, method="GET", body=None):
        calls.append((url, method, body))
        if url.endswith("/api/demo/incidents"):
            return {"incidents": [{"id": sid, "prepared_input": f"data/{sid}.json"}
                                  for sid in profile.SCENARIO_IDS]}
        if method == "POST":
            return {"analysis_id": body["incident_id"], "status": "queued"}
        return {"status": "completed"}

    completed = profile._exercise("http://profile.test", request_fn=fake_request)
    assert completed == list(profile.SCENARIO_IDS)
    submitted = [body["incident_id"] for _, method, body in calls if method == "POST"]
    polled = [url.rsplit("/", 1)[-1] for url, method, _ in calls
              if method == "GET" and "/api/demo/analyses/" in url]
    assert submitted == list(profile.SCENARIO_IDS)
    assert polled == list(profile.SCENARIO_IDS)


def test_report_fails_if_any_trial_has_no_docker_stats_samples():
    trials = [
        {"trial": n, "peak_memory_bytes": 0, "peak_cpu_percent": 0,
         "stats_samples": ["10MiB / 1GiB|1%"] if n != 2 else [],
         "scenarios_completed": profile.SCENARIO_IDS}
        for n in range(1, 4)
    ]
    try:
        profile.build_report(trials, image_sizes={}, disk={})
    except ValueError as error:
        assert "stats" in str(error).lower()
    else:
        raise AssertionError("missing per-trial Docker samples must invalidate the profile")


def test_profile_fails_when_docker_stats_collection_errors():
    try:
        profile.require_stats_samples(2, [], ["Docker stats sampling failed"])
    except RuntimeError as error:
        assert "stats" in str(error).lower()
    else:
        raise AssertionError("Docker stats errors must fail the profile")


def test_combined_stats_sum_backend_and_frontend_resources():
    output = "backend|120MiB / 1GiB|35.0%\nfrontend|80MiB / 1GiB|12.5%"
    expected = ("backend", "frontend")
    assert profile.aggregate_docker_stats_output(output, expected_container_names=expected) == (
        200 * 1024 * 1024, 47.5,
    )
    try:
        profile.aggregate_docker_stats_output("backend|120MiB / 1GiB|35.0%",
                                              expected_container_names=expected)
    except ValueError as error:
        assert "every expected" in str(error)
    else:
        raise AssertionError("missing frontend sample must be rejected")


def test_disk_calculation_includes_current_and_replacement_image_pairs():
    result = profile.calculate_disk_footprint(
        image_sizes={"backend": {"unpacked": 100, "archive": 20},
                     "frontend": {"unpacked": 50, "archive": 10}},
        existing_used_bytes=400,
    )
    assert result["replacement_peak_image_bytes"] == 360
    assert result["required_volume_bytes_with_25pct_free"] == 1014
