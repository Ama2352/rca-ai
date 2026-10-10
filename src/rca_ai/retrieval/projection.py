"""RCA-owned search projection over canonical observations.

This boundary decides how observations participate in H/K search. Keeping the
policy here lets the Processor report every observation while preserving the
current deterministic modality renderer and retrieval algorithms.
"""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any

from rca_ai.domain.models import CanonicalIncidentEvidence
from rca_ai.retrieval.query import build_retrieval_query


_CONTROL_SCOPE = re.compile(r"(?:feature[._ -]?flag|flagd|experiment|fault[._ -]?inject|chaos)", re.I)
_CONTROL_NOUN = re.compile(r"(?:feature[._ -]?flag|flagd|experiment|simulation|injection|problem[._ -]?pattern)", re.I)
_STATE_VERB = re.compile(r"\b(?:enabled|disabled|activated|deactivated|toggled|overridden|inject(?:ed|ing)?|simulat(?:ed|ing|ion))\b", re.I)
_EXPLICIT_SIMULATION = re.compile(r"\b(?:for|of|during|starting|ending|completed?|done with)\b.{0,80}\bsimulation\b", re.I)
_SIGNALS = ("metric", "log", "trace", "kubernetes")
_PAYLOAD_KEYS = {"metric": "metrics", "log": "logs", "trace": "traces", "kubernetes": "kubernetes"}


@dataclass(frozen=True)
class RetrievalProjection:
    """Internal retrieval payload and deterministic audit metadata."""

    payload: dict[str, Any]
    query: str
    included_counts: dict[str, int]
    excluded_observations: tuple[tuple[str, str], ...]


def _control_narration_reason(value: dict[str, Any]) -> str | None:
    scope = str(value.get("scope") or "")
    message = str(value.get("example") or value.get("pattern") or "")
    if _CONTROL_SCOPE.search(scope):
        return "control_or_injection_narration"
    if _CONTROL_NOUN.search(message) and (_STATE_VERB.search(message) or _EXPLICIT_SIMULATION.search(message)):
        return "control_or_injection_narration"
    return None


def project_retrieval(evidence: CanonicalIncidentEvidence) -> RetrievalProjection:
    """Render selected canonical observations using generic RCA search policy."""
    payload: dict[str, Any] = {
        "window": dict(evidence.window),
        "metrics": [], "logs": [], "traces": [], "kubernetes": [],
    }
    counts = {signal: 0 for signal in _SIGNALS}
    excluded: list[tuple[str, str]] = []
    for observation in evidence.observations:
        if observation.signal not in _PAYLOAD_KEYS:
            raise ValueError(f"Unsupported canonical signal: {observation.signal}")
        row = dict(observation.value) if isinstance(observation.value, dict) else None
        if row is None:
            raise ValueError(f"Canonical {observation.signal} observation value must be an object")
        if observation.signal == "log":
            reason = _control_narration_reason(row)
            if reason:
                excluded.append((observation.observation_id, reason))
                continue
            # Eligibility is a Core decision, not an input fact from Processor.
            row["retrieval_eligible"] = True
        payload[_PAYLOAD_KEYS[observation.signal]].append(row)
        counts[observation.signal] += 1
    query = build_retrieval_query(payload)
    return RetrievalProjection(payload, query, counts, tuple(excluded))
