from copy import deepcopy
from pathlib import Path

from rca_ai.domain.models import (
    CanonicalIncidentEvidence,
    CanonicalObservation,
    EvidenceEntity,
    EvidenceSource,
    IncidentInput,
    to_dict,
)
from rca_ai.facts.builder import build_fact_view
from rca_ai.retrieval.projection import project_retrieval


def _observation(oid, signal, field, value, source_ref):
    return CanonicalObservation(
        observation_id=oid,
        signal=signal,
        entity=EvidenceEntity("service", "ad"),
        field=field,
        value=value,
        attributes={},
        source=EvidenceSource(source_ref, f"/{signal}/{oid}", (f"{signal}.json:{oid}",)),
    )


def test_control_narration_is_search_excluded_but_remains_current_fact():
    control = _observation("o1", "log", "log.info_change", {
        "lane": "log.info_change", "service": "ad", "severity": "INFO",
        "pattern": "High CPU-Load problempattern enabled", "example": "High CPU-Load problempattern enabled",
        "scope": "oteldemo.problempattern.CPULoad", "baseline_count": 1, "incident_count": 12,
        "signed_rate_change": 5.25,
    }, "s1")
    ordinary = _observation("o2", "log", "log.info_change", {
        "lane": "log.info_change", "service": "ad", "severity": "INFO",
        "pattern": "Targeted ad request received", "example": "Targeted ad request received",
        "scope": "oteldemo.AdService", "baseline_count": 0, "incident_count": 2,
        "signed_rate_change": 1.0,
    }, "s2")
    evidence = CanonicalIncidentEvidence({}, (control, ordinary))
    before = to_dict(evidence)

    facts = build_fact_view(IncidentInput("ad-high-cpu-01", evidence))
    result = project_retrieval(evidence)

    assert [fact.source_ref for fact in facts] == ["s1", "s2"]
    assert result.excluded_observations == (("o1", "control_or_injection_narration"),)
    assert len(result.payload["logs"]) == 1
    assert result.payload["logs"][0]["pattern"] == "Targeted ad request received"
    assert to_dict(evidence) == before


def test_retrieval_projection_is_deterministic_and_keeps_signal_namespaces():
    metric = _observation("o1", "metric", "metric.gauge_absolute", {
        "lane": "metric.gauge_absolute", "service": "checkout", "metric": "cpu_usage",
        "metric_kind": "gauge", "labels": {}, "signed_change": 0.5,
        "baseline_value": 0.1, "incident_value": 0.6, "unit": "cores", "uncertainty": [],
    }, "s1")
    evidence = CanonicalIncidentEvidence({"baseline_start": 1}, (metric,))

    first = project_retrieval(evidence)
    second = project_retrieval(evidence)

    assert first == second
    assert first.query == (
        "METRIC lane=metric.gauge_absolute service=checkout metric=cpu_usage type=gauge "
        "direction=increased unit=cores before=0.1 incident=0.6\n"
    )
    assert first.included_counts == {"metric": 1, "log": 0, "trace": 0, "kubernetes": 0}


def test_search_policy_has_no_scenario_name_routing():
    source = Path(__file__).resolve().parents[3] / "src" / "rca_ai" / "retrieval" / "projection.py"
    text = source.read_text(encoding="utf-8")
    assert all(name not in text for name in ("missing-secret-01", "application-failure-01", "ad-high-cpu-01"))
    assert "retrieval_eligible" in text
