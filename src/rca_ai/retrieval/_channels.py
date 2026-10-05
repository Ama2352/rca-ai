"""Frozen canonical-text parser, modality views, and reciprocal-rank fusion."""

from __future__ import annotations

import json
import math
import re
from collections.abc import Iterable, Mapping
from typing import Any

CHANNELS = ("METRIC", "LOG", "TRACE", "KUBERNETES")
_FIELD = re.compile(r'([\w.]+)=("(?:\\.|[^"\\])*"|[^\s"]+)')


def parse(text: str):
    for line in text.splitlines():
        if not line.strip():
            continue
        channel, _, body = line.partition(" ")
        if channel not in CHANNELS:
            raise ValueError("Unknown modality")
        fields: dict[str, Any] = {}
        position = 0
        for match in _FIELD.finditer(body):
            if body[position:match.start()].strip():
                raise ValueError("Malformed canonical field")
            key, value = match.groups()
            if key in fields:
                raise ValueError("Duplicate canonical key")
            fields[key] = json.loads(value) if value.startswith('"') else value
            position = match.end()
        if body[position:].strip():
            raise ValueError("Malformed canonical tail")
        yield channel, fields


def _normalize(value: str) -> str:
    value = {"increased": "increase", "decreased": "decrease"}.get(value, value)
    value = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1 \2", value)
    value = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", value)
    return " ".join(re.findall(r"[^\W_]+", value, re.UNICODE)).lower()


def render_channels(text: str, normalized: bool = False) -> dict[str, str]:
    lines: dict[str, list[str]] = {channel: [] for channel in CHANNELS}
    for channel, fields in parse(text):
        parts: list[str] = []

        def add(key: str, role: str | None = None, free: bool = False) -> None:
            if key in fields:
                value = fields[key]
                if normalized and not free:
                    value = _normalize(value)
                parts.extend(([role] if role else []) + [value])

        if channel == "METRIC":
            for key in ("service", "metric", "type", "direction", "unit"):
                add(key)
            for key in sorted(key for key in fields if key.startswith("label.")):
                add(key, _normalize(key[6:]) if normalized else key[6:])
            add("support", "support")
        elif channel == "LOG":
            for key in ("service", "severity", "change"):
                add(key)
            add("pattern", free=True)
        elif channel == "TRACE":
            add("kind")
            add("service")
            for key in ("callee", "operation", "error", "latency", "attribution"):
                add(key, key)
        else:
            add("workload")
            for key in ("container", "phase", "ready", "state", "reason", "termination_reason", "exit_code", "event", "replicas"):
                add(key, _normalize(key) if normalized else key)
        line = " ".join(" ".join(parts).split())
        if line:
            lines[channel].append(line)
    return {channel: "\n".join(rows) + ("\n" if rows else "") for channel, rows in lines.items()}


def fuse(channels: Mapping[str, Iterable[Mapping[str, Any]]], *, k: int = 60) -> list[dict[str, Any]]:
    by_id: dict[str, dict[str, int]] = {}
    for channel in sorted(channels):
        for row in channels[channel]:
            by_id.setdefault(str(row["incident_id"]), {})[channel] = int(row["rank"])
    items = []
    for incident_id, ranks in by_id.items():
        contributions = {channel: 1 / (k + rank) for channel, rank in sorted(ranks.items())}
        items.append((incident_id, math.fsum(contributions.values()), contributions, ranks))
    items.sort(key=lambda row: (-row[1], row[0]))
    return [
        {"rank": rank, "incident_id": incident_id, "rrf_score": score,
         "contributions": contributions, "channel_ranks": dict(ranks)}
        for rank, (incident_id, score, contributions, ranks) in enumerate(items, 1)
    ]
