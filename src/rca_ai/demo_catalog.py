"""Validated metadata for collected scenarios and runnable prepared inputs."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
CATALOG_PATH = PROJECT_ROOT / "data" / "scenarios" / "catalog.json"
SUPPORTED_SOURCES = {"otel-demo", "custom-k8s"}
SUPPORTED_READINESS = {"demo-ready", "experimental", "unverified"}


def _validate_snapshot_references(row: dict[str, Any], fixture: dict[str, Any], root: Path) -> None:
    """Match curated IDs to both prepared observations and the existing selection audit."""

    scenario_id = row["id"]
    ids = row.get("snapshot_observation_ids")
    if not isinstance(ids, list) or not ids or any(not isinstance(item, str) for item in ids):
        raise ValueError(f"prepared scenario requires snapshot observation IDs: {scenario_id}")
    if len(ids) != len(set(ids)):
        raise ValueError(f"duplicate snapshot observation ID: {scenario_id}")
    manifest_path = root / "data" / "demo" / "selection_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    audit = manifest["scenarios"][scenario_id]
    if audit["input_file"] != Path(row["prepared_input"]).name:
        raise ValueError(f"selection manifest input mismatch: {scenario_id}")
    included = {item["observation_id"]: item for item in audit["included_observations"]}
    observations = {item["observation_id"]: item for item in fixture["evidence"]["observations"]}
    for observation_id in ids:
        observation = observations.get(observation_id)
        record = included.get(observation_id)
        if observation is None or record is None:
            raise ValueError(f"unresolved snapshot observation: {scenario_id}/{observation_id}")
        if any((
            observation["signal"] != record["signal"],
            observation["field"] != record["field"],
            observation["entity"] != record["entity"],
            observation["source"]["source_ref"] != record["source_ref"],
            observation["source"]["source_path"] != record["source_path"],
        )):
            raise ValueError(f"snapshot observation differs from selection manifest: {scenario_id}/{observation_id}")


def load_scenario_catalog(
    catalog_path: Path = CATALOG_PATH,
    *,
    project_root: Path = PROJECT_ROOT,
) -> list[dict[str, Any]]:
    """Load and validate catalog identity, classification, and runnable inputs."""

    rows = json.loads(catalog_path.read_text(encoding="utf-8"))
    if not isinstance(rows, list):
        raise ValueError("scenario catalog must be a JSON array")

    seen: set[str] = set()
    root = project_root.resolve()
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("scenario catalog entries must be objects")
        scenario_id = row.get("id")
        if not isinstance(scenario_id, str) or not scenario_id.strip():
            raise ValueError("scenario id must be a non-empty string")
        if scenario_id in seen:
            raise ValueError(f"duplicate scenario id: {scenario_id}")
        seen.add(scenario_id)
        source = row.get("source")
        if not isinstance(source, str) or source not in SUPPORTED_SOURCES:
            raise ValueError(f"unsupported scenario source: {row.get('source')}")
        readiness = row.get("readiness")
        if not isinstance(readiness, str) or readiness not in SUPPORTED_READINESS:
            raise ValueError(f"unsupported readiness: {readiness}")
        if not isinstance(row.get("title"), str) or not row["title"].strip():
            raise ValueError(f"scenario title must be a non-empty string: {scenario_id}")

        prepared_input = row.get("prepared_input")
        if readiness == "demo-ready" and not isinstance(prepared_input, str):
            raise ValueError(f"demo-ready scenario requires prepared_input: {scenario_id}")
        if prepared_input is not None:
            if not isinstance(prepared_input, str) or not prepared_input.strip():
                raise ValueError(f"prepared_input must be a non-empty path or null: {scenario_id}")
            path = Path(prepared_input)
            if path.is_absolute():
                raise ValueError(f"prepared input must be repository-relative: {scenario_id}")
            resolved = (root / path).resolve()
            if not resolved.is_relative_to(root):
                raise ValueError(f"prepared input must stay inside the repository: {scenario_id}")
            if not resolved.is_file():
                raise ValueError(f"prepared input does not exist: {prepared_input}")
            try:
                fixture = json.loads(resolved.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as error:
                raise ValueError(f"prepared input is not valid JSON: {prepared_input}") from error
            if not isinstance(fixture, dict) or fixture.get("incident_id") != scenario_id:
                raise ValueError(f"prepared input incident ID mismatch: {scenario_id}")
            _validate_snapshot_references(row, fixture, root)
            if not isinstance(row.get("description"), str) or not row["description"].strip():
                raise ValueError(f"runnable scenario requires description: {scenario_id}")
            for field in ("affected_services", "symptoms", "investigation_focus"):
                if not isinstance(row.get(field), list) or not row[field]:
                    raise ValueError(f"runnable scenario requires {field}: {scenario_id}")
        elif "snapshot_observation_ids" in row:
            raise ValueError(f"scenario without prepared input must not define snapshot: {scenario_id}")

    return rows


SCENARIO_CATALOG = load_scenario_catalog()
SCENARIOS_BY_ID = {row["id"]: row for row in SCENARIO_CATALOG}


def demo_ready_scenario_ids() -> tuple[str, ...]:
    """Return quality-verified IDs from the validated catalog, preserving order."""

    return tuple(
        row["id"] for row in SCENARIO_CATALOG
        if row["readiness"] == "demo-ready"
    )


def runnable_scenario_ids() -> tuple[str, ...]:
    """Return scenarios whose fixture passed catalog and manifest validation."""

    return tuple(row["id"] for row in SCENARIO_CATALOG if row["prepared_input"] is not None)
