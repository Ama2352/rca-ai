#!/usr/bin/env python3
"""Offline resource profiler for the production RCA image pair.

This tool uses Docker only. The workload container mounts offline_profile_app.py
read-only and injects fake providers; it refuses provider credentials before
making any Docker calls.
"""

from __future__ import annotations

import argparse
import gzip
import json
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from typing import Any, Mapping, Sequence
from urllib.error import URLError
from urllib.request import Request, urlopen


SCENARIO_IDS = (
    "missing-secret-01", "application-failure-01", "ad-high-cpu-01",
    "cart-failure-01", "dependency-unavailable-01", "downstream-latency-01",
    "memory-leak-01", "messaging-failure-01", "crash-loop-backoff-01",
)
PROVIDER_KEY_NAMES = ("GROQ_API_KEY", "CEREBRAS_API_KEY")


def provider_keys_present(environment: Mapping[str, str]) -> bool:
    return any(environment.get(name, "").strip() for name in PROVIDER_KEY_NAMES)


def calculate_disk_footprint(
    *, image_sizes: Mapping[str, Mapping[str, int]], existing_used_bytes: int
) -> dict[str, int]:
    one_pair = sum(int(row["unpacked"]) + int(row["archive"]) for row in image_sizes.values())
    two_pairs = one_pair * 2
    # During replacement, Docker retains the running pair while pulling the next pair.
    used_with_images = max(0, existing_used_bytes) + two_pairs
    return {
        "one_image_pair_bytes": one_pair,
        "replacement_peak_image_bytes": two_pairs,
        "existing_used_bytes": max(0, existing_used_bytes),
        "required_volume_bytes_with_25pct_free": math.ceil(used_with_images / 0.75),
    }


def build_report(
    trials: Sequence[Mapping[str, Any]],
    *,
    image_sizes: Mapping[str, Mapping[str, int]],
    disk: Mapping[str, int],
) -> dict[str, Any]:
    if len(trials) < 3:
        raise ValueError("at least three trials are required")
    coverage = set()
    for trial in trials:
        trial_coverage = tuple(trial.get("scenarios_completed", ()))
        if trial_coverage != SCENARIO_IDS:
            missing = set(SCENARIO_IDS) - set(trial_coverage)
            extra = set(trial_coverage) - set(SCENARIO_IDS)
            raise ValueError(
                f"scenario coverage invalid in trial {trial.get('trial')}: "
                f"missing={','.join(sorted(missing))}; extra={','.join(sorted(extra))}"
            )
        coverage.update(trial_coverage)
    all_samples = []
    normalized_trials = []
    for trial in trials:
        samples = trial.get("stats_samples", ())
        if not samples:
            raise ValueError(f"Docker stats are missing for trial {trial.get('trial')}")
        parsed_samples = [aggregate_docker_stats_output(sample) for sample in samples]
        trial_peak_memory = max(row[0] for row in parsed_samples)
        trial_peak_cpu = max(row[1] for row in parsed_samples)
        all_samples.extend(parsed_samples)
        normalized_trials.append({
            **trial,
            "peak_memory_bytes": trial_peak_memory,
            "peak_cpu_percent": trial_peak_cpu,
            "sample_count": len(parsed_samples),
        })
    peak_memory = max(row[0] for row in all_samples)
    peak_cpu = max(row[1] for row in all_samples)
    return {
        "profile_version": 1,
        "provider_mode": "offline_fakes",
        "trial_count": len(trials),
        "scenario_coverage": [sid for sid in SCENARIO_IDS if sid in coverage],
        "trials": normalized_trials,
        "peaks": {
            "memory_bytes": peak_memory,
            "cpu_percent": peak_cpu,
        },
        "image_sizes": dict(image_sizes),
        "disk": dict(disk),
        "resource_method": {
            "memory": "maximum one-second sample of backend plus frontend container memory",
            "cpu": "maximum one-second sample of summed backend plus frontend CPU percentages",
        },
    }


def _docker(*args: str, capture: bool = True) -> str:
    result = subprocess.run(["docker", *args], check=True, text=True,
                            stdout=subprocess.PIPE if capture else None,
                            stderr=subprocess.PIPE if capture else None)
    return result.stdout.strip() if capture else ""


def _parse_size(value: str) -> int:
    match = re.fullmatch(r"\s*([\d.]+)\s*(B|KB|MB|GB|KiB|MiB|GiB)\s*", value, re.I)
    if not match:
        raise ValueError(f"unsupported Docker stats size: {value!r}")
    scale = {"b": 1, "kb": 1000, "mb": 1000**2, "gb": 1000**3,
             "kib": 1024, "mib": 1024**2, "gib": 1024**3}[match.group(2).lower()]
    return int(float(match.group(1)) * scale)


def parse_docker_stats_output(output: str) -> tuple[int, float]:
    """Parse one fakeable `docker stats --format '{{.MemUsage}}|{{.CPUPerc}}'` row."""
    memory, cpu = output.strip().split("|", 1)
    return _parse_size(memory.split("/", 1)[0].strip()), float(cpu.strip().rstrip("%"))


def aggregate_docker_stats_output(
    output: str, *, expected_container_names: Sequence[str] | None = None,
) -> tuple[int, float]:
    """Sum contemporaneous memory/CPU samples for every running app container."""
    lines = output.strip().splitlines()
    if not lines:
        raise ValueError("Docker stats output is empty")
    rows = []
    names = set()
    for line in lines:
        fields = line.split("|")
        if len(fields) == 2:
            rows.append(parse_docker_stats_output(line))
        elif len(fields) == 3:
            name, memory, cpu = fields
            if name in names:
                raise ValueError(f"duplicate Docker stats row: {name}")
            names.add(name)
            rows.append(parse_docker_stats_output(f"{memory}|{cpu}"))
        else:
            raise ValueError(f"invalid Docker stats row: {line!r}")
    if len(lines) > 1 and len(names) != len(lines):
        raise ValueError("Docker stats rows must consistently include container names")
    if expected_container_names is not None and names != set(expected_container_names):
        raise ValueError("Docker stats did not include every expected application container")
    return sum(row[0] for row in rows), sum(row[1] for row in rows)


def require_stats_samples(
    trial_number: int, samples: Sequence[str], errors: Sequence[str],
) -> None:
    if errors:
        raise RuntimeError(f"Docker stats sampling failed for trial {trial_number}")
    if not samples:
        raise RuntimeError(f"Docker stats returned no samples for trial {trial_number}")


def _image_size(reference: str, archive_dir: Path) -> dict[str, Any]:
    unpacked, architecture = _docker("image", "inspect", "--format", "{{.Size}}|{{.Architecture}}", reference).split("|", 1)
    archive = archive_dir / (re.sub(r"[^A-Za-z0-9_.-]", "_", reference) + ".tar")
    saved = subprocess.Popen(["docker", "image", "save", reference], stdout=subprocess.PIPE)
    assert saved.stdout is not None
    with archive.open("wb") as output:
        with gzip.GzipFile(fileobj=output, mode="wb", compresslevel=6) as compressed:
            shutil.copyfileobj(saved.stdout, compressed)
    if saved.wait() != 0:
        raise subprocess.CalledProcessError(saved.returncode or 1, ["docker", "image", "save", reference])
    result = {"unpacked": int(unpacked), "archive": archive.stat().st_size,
              "architecture": architecture}
    archive.unlink()
    return result


def _request(base: str, method: str = "GET", body: dict[str, Any] | None = None) -> Any:
    payload = json.dumps(body).encode() if body is not None else None
    request = Request(base, data=payload, method=method,
                      headers={"Content-Type": "application/json"})
    with urlopen(request, timeout=8) as response:
        return json.loads(response.read())


def _wait_ready(base: str, timeout: float = 90) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            _request(base + "/api/demo/health")
            return
        except (URLError, TimeoutError, OSError):
            time.sleep(0.5)
    raise TimeoutError("offline backend did not become ready within 90 seconds")


def _exercise(base: str, *, request_fn=_request) -> list[str]:
    catalog = request_fn(base + "/api/demo/incidents")["incidents"]
    runnable = {row["id"] for row in catalog if row.get("prepared_input")}
    if runnable != set(SCENARIO_IDS):
        raise ValueError("backend prepared scenario catalog does not match the nine expected scenarios")
    completed: list[str] = []
    for scenario_id in SCENARIO_IDS:
        result = request_fn(base + "/api/demo/analyses", "POST", {"incident_id": scenario_id})
        analysis_id = result["analysis_id"]
        deadline = time.monotonic() + 60
        while time.monotonic() < deadline:
            job = request_fn(base + f"/api/demo/analyses/{analysis_id}")
            if job["status"] == "completed":
                break
            if job["status"] == "failed":
                raise RuntimeError(f"offline analysis failed for {scenario_id}: {job.get('error', {}).get('code', 'unknown')}")
            time.sleep(0.1)
        else:
            raise TimeoutError(f"offline analysis timed out for {scenario_id}")
        completed.append(scenario_id)
    return completed


def _run_trial(number: int, backend_image: str, frontend_image: str, harness_path: Path) -> dict[str, Any]:
    suffix = f"{os.getpid()}-{number}"
    backend_name = f"rca-profile-{suffix}-backend"
    frontend_name = f"rca-profile-{suffix}-frontend"
    network_name = f"rca-profile-{suffix}"
    _docker("network", "create", network_name)
    backend_id = None
    frontend_id = None
    samples: list[str] = []
    stats_errors: list[str] = []
    try:
        backend_id = _docker(
            "run", "--detach", "--name", backend_name, "--network", network_name,
            "--network-alias", "backend", "--publish", "127.0.0.1::8000",
            "--mount", f"type=bind,src={harness_path.resolve()},dst=/tmp/offline_profile_app.py,readonly",
            "--entrypoint", "python", backend_image,
            "/tmp/offline_profile_app.py", "--host", "0.0.0.0", "--port", "8000",
        )
        frontend_id = _docker(
            "run", "--detach", "--name", frontend_name, "--network", network_name,
            "--env", "RCA_DEMO_HOST=:80", "--publish", "127.0.0.1::80", frontend_image,
        )
    except Exception:
        for container in (frontend_id, backend_id):
            if container:
                subprocess.run(["docker", "rm", "--force", container], check=False,
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        _docker("network", "rm", network_name)
        raise
    stop = threading.Event()

    def sample() -> None:
        while not stop.is_set():
            try:
                row = _docker(
                    "stats", "--no-stream", "--format", "{{.Name}}|{{.MemUsage}}|{{.CPUPerc}}",
                    backend_name, frontend_name,
                )
                aggregate_docker_stats_output(
                    row, expected_container_names=(backend_name, frontend_name),
                )
                samples.append(row)
            except (subprocess.SubprocessError, OSError, ValueError, IndexError):
                stats_errors.append("Docker stats sampling failed")
                return
            stop.wait(1)

    sampler = threading.Thread(target=sample, daemon=True)
    started = time.monotonic()
    try:
        port = _docker("port", frontend_id, "80/tcp").rsplit(":", 1)[-1]
        base = f"http://127.0.0.1:{port}"
        sampler.start()
        _wait_ready(base)
        cold_start_seconds = time.monotonic() - started
        scenarios = _exercise(base)
        restart_started = time.monotonic()
        _docker("restart", backend_id)
        _wait_ready(base)
        restart_seconds = time.monotonic() - restart_started
        _request(base + "/api/demo/incidents")
        if not samples and not stats_errors:
            stop.wait(1.05)
        stop.set()
        sampler.join(timeout=2)
        require_stats_samples(number, samples, stats_errors)
        parsed_samples = [aggregate_docker_stats_output(row) for row in samples]
        return {
            "trial": number, "scenarios_completed": scenarios,
            "cold_start_seconds": round(cold_start_seconds, 3),
            "restart_seconds": round(restart_seconds, 3),
            "peak_memory_bytes": max(row[0] for row in parsed_samples),
            "peak_cpu_percent": max(row[1] for row in parsed_samples),
            "sample_count": len(samples),
            "stats_samples": samples,
        }
    finally:
        stop.set()
        if sampler.is_alive():
            sampler.join(timeout=2)
        for container in (frontend_id, backend_id):
            if container:
                subprocess.run(["docker", "rm", "--force", container], check=False,
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        subprocess.run(["docker", "network", "rm", network_name], check=False,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--compose", default="compose.prod.yaml", help="production Compose file (validated as an input record)")
    parser.add_argument("--backend-image", default=os.getenv("BACKEND_IMAGE"))
    parser.add_argument("--frontend-image", default=os.getenv("FRONTEND_IMAGE"))
    parser.add_argument("--output", type=Path, default=Path("/tmp/rca-profile.json"))
    parser.add_argument("--trials", type=int, default=3)
    parser.add_argument("--existing-used-bytes", type=int, default=0,
                        help="measured used bytes on the target Linux root volume; not inferred from this host")
    args = parser.parse_args(argv)
    if provider_keys_present(os.environ):
        print("Refusing to profile while provider credentials are present; values are never displayed.", file=sys.stderr)
        return 2
    if args.trials < 3:
        parser.error("--trials must be at least 3")
    if not args.backend_image or not args.frontend_image:
        parser.error("supply --backend-image and --frontend-image for locally built images")
    compose = Path(args.compose)
    if not compose.is_file():
        parser.error(f"Compose file not found: {compose}")
    harness_path = Path(__file__).with_name("offline_profile_app.py")
    if not harness_path.is_file():
        parser.error("offline harness is missing")
    try:
        _docker("version", "--format", "{{.Server.Version}}")
    except (FileNotFoundError, subprocess.CalledProcessError) as error:
        print("Docker Engine is unavailable; run this command on the Linux Docker host.", file=sys.stderr)
        return 3

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="rca-image-profile-") as tmp:
        image_sizes = {
            "backend": _image_size(args.backend_image, Path(tmp)),
            "frontend": _image_size(args.frontend_image, Path(tmp)),
        }
        architectures = {row["architecture"] for row in image_sizes.values()}
        if len(architectures) != 1:
            parser.error("frontend/backend image architectures differ")
        disk = calculate_disk_footprint(image_sizes=image_sizes, existing_used_bytes=args.existing_used_bytes)
        trials = [_run_trial(index + 1, args.backend_image, args.frontend_image, harness_path)
                  for index in range(args.trials)]
    report = build_report(trials, image_sizes=image_sizes, disk=disk)
    report["architecture"] = next(iter(architectures))
    report["compose_file"] = str(compose)
    report["host_root_volume_fit"] = "not assessed; provide target host used bytes and volume size"
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"Profile written to {args.output}; no provider credentials were used.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
