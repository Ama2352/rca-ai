from __future__ import annotations

import json
from pathlib import Path

import pytest

from rca_ai.demo_catalog import load_scenario_catalog


ROOT = Path(__file__).resolve().parents[2]


def test_catalog_describes_nine_captures_and_runnable_prepared_inputs():
    rows = load_scenario_catalog()

    editorial_fields = {"title", "description", "affected_services", "symptoms", "investigation_focus"}
    assert all(editorial_fields.isdisjoint(row) for row in rows)

    assert len(rows) == 9
    assert {row["id"] for row in rows} == {
        "ad-high-cpu-01", "application-failure-01", "cart-failure-01",
        "dependency-unavailable-01", "downstream-latency-01", "memory-leak-01",
        "messaging-failure-01", "missing-secret-01", "crash-loop-backoff-01",
    }
    assert sum(row["source"] == "otel-demo" for row in rows) == 7
    assert sum(row["source"] == "custom-k8s" for row in rows) == 2
    ready = [row for row in rows if row["readiness"] == "demo-ready"]
    assert {row["id"] for row in ready} == {
        "ad-high-cpu-01", "application-failure-01", "cart-failure-01",
        "dependency-unavailable-01", "memory-leak-01", "messaging-failure-01",
        "missing-secret-01",
    }
    assert len(ready) == 7
    assert {row["id"] for row in rows if row["readiness"] == "experimental"} == {
        "crash-loop-backoff-01", "downstream-latency-01",
    }
    runnable = [row for row in rows if row["prepared_input"] is not None]
    assert len(runnable) == 9
    assert all((ROOT / row["prepared_input"]).is_file() for row in runnable)
    assert all(row["prepared_input"] is None for row in rows if row["readiness"] == "unverified")


def test_all_demo_observations_match_selection_manifest_provenance():
    rows = load_scenario_catalog()
    manifest = json.loads((ROOT / "data/demo/selection_manifest.json").read_text(encoding="utf-8"))
    for row in rows:
        if row["prepared_input"] is None:
            continue
        fixture = json.loads((ROOT / row["prepared_input"]).read_text(encoding="utf-8"))
        listed = manifest["scenarios"][row["id"]]["included_observations"]
        assert {item["observation_id"] for item in listed} == {
            item["observation_id"] for item in fixture["evidence"]["observations"]
        }
        by_id = {item["observation_id"]: item for item in listed}
        for observation in fixture["evidence"]["observations"]:
            entry = by_id[observation["observation_id"]]
            assert observation["signal"] == entry["signal"]
            assert observation["entity"] == entry["entity"]
            assert observation["field"] == entry["field"]
            assert observation["source"]["source_ref"] == entry["source_ref"]
            assert observation["source"]["source_path"] == entry["source_path"]
            assert observation["source"]["locators"] == entry["locators"]


@pytest.mark.parametrize(
    "mutate, message",
    [
        (lambda rows: rows.append(rows[0].copy()), "duplicate scenario id"),
        (lambda rows: rows[0].update(source="unknown"), "unsupported scenario source"),
        (lambda rows: rows[0].update(readiness="failed"), "unsupported readiness"),
        (lambda rows: rows[0].update(description="editorial prose"), "unsupported scenario catalog fields"),
        (lambda rows: rows[0].update(prepared_input="data/demo/not-present.json"), "prepared input does not exist"),
    ],
)
def test_catalog_rejects_invalid_records(tmp_path, mutate, message):
    rows = json.loads((ROOT / "data/scenarios/catalog.json").read_text(encoding="utf-8"))
    mutate(rows)
    path = tmp_path / "catalog.json"
    path.write_text(json.dumps(rows), encoding="utf-8")

    with pytest.raises(ValueError, match=message):
        load_scenario_catalog(path, project_root=ROOT)


def test_snapshot_reference_must_exist_in_fixture_and_manifest(tmp_path):
    rows = json.loads((ROOT / "data/scenarios/catalog.json").read_text(encoding="utf-8"))
    rows[0]["snapshot_observation_ids"] = ["not-an-observation"]
    path = tmp_path / "catalog.json"
    path.write_text(json.dumps(rows), encoding="utf-8")
    with pytest.raises(ValueError, match="unresolved snapshot observation"):
        load_scenario_catalog(path, project_root=ROOT)


def test_snapshot_metadata_cannot_duplicate_telemetry_values():
    rows = load_scenario_catalog()
    for row in rows:
        if row["prepared_input"] is not None:
            assert set(row["snapshot_observation_ids"])
            assert not any("value" in key or "unit" in key for key in row)
        else:
            assert "snapshot_observation_ids" not in row


def test_catalog_retains_only_registry_and_integrity_metadata():
    rows = load_scenario_catalog()
    allowed = {"id", "source", "readiness", "prepared_input", "snapshot_observation_ids"}
    assert all(set(row) <= allowed for row in rows)


def test_experimental_scenario_with_prepared_fixture_passes_manifest_validation(tmp_path):
    rows = json.loads((ROOT / "data/scenarios/catalog.json").read_text(encoding="utf-8"))
    downstream = next(row for row in rows if row["id"] == "downstream-latency-01")
    downstream["prepared_input"] = "data/demo/downstream-latency-01.json"
    downstream["snapshot_observation_ids"] = [
        "f7182f3b9b1e689770d30c83", "6b8d40add3516e60450d8828",
        "611b0d58e2add4341daca248", "9e960391a10072755e12e297",
    ]
    path = tmp_path / "catalog.json"
    path.write_text(json.dumps(rows), encoding="utf-8")

    loaded = load_scenario_catalog(path, project_root=ROOT)
    scenario = next(row for row in loaded if row["id"] == "downstream-latency-01")
    assert scenario["readiness"] == "experimental"
    assert scenario["prepared_input"] == "data/demo/downstream-latency-01.json"


def test_catalog_accepts_readiness_classification_without_prepared_input(tmp_path):
    rows = json.loads((ROOT / "data/scenarios/catalog.json").read_text(encoding="utf-8"))
    ready_without_fixture = next(row for row in rows if row["id"] == "missing-secret-01")
    ready_without_fixture["prepared_input"] = None
    ready_without_fixture.pop("snapshot_observation_ids")
    path = tmp_path / "catalog.json"
    path.write_text(json.dumps(rows), encoding="utf-8")

    loaded = load_scenario_catalog(path, project_root=ROOT)
    row = next(row for row in loaded if row["id"] == "missing-secret-01")
    assert row["readiness"] == "demo-ready"
    assert row["prepared_input"] is None
