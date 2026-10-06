import json
from pathlib import Path

import pytest

from rca_ai.domain.models import Fact, FactEntity, to_dict
from rca_ai.facts.selector import request_bytes, select_facts


ROOT = Path(__file__).resolve().parents[3]
FIXTURES = ROOT / "tests" / "fixtures" / "facts"
CASES = (
    ("missing-secret-01", 9186),
    ("application-failure-01", 8082),
    ("ad-high-cpu-01", 8750),
)


def _load_selection_case(incident_id):
    rows = json.loads(
        (FIXTURES / "expected" / "fact_views" / f"{incident_id}.json").read_text(encoding="utf-8")
    )["facts"]
    facts = tuple(Fact(
        row["fact_id"], FactEntity(**row["entity"]), row["field"], row["value"],
        row["source_ref"], row["source_path"],
    ) for row in rows)
    expected = json.loads(
        (FIXTURES / "expected" / "selections" / f"{incident_id}.json").read_text(encoding="utf-8")
    )
    return facts, expected


def _request_size_for(empty_request_bytes):
    """Model the frozen user's JSON-in-string fact payload byte delta.

    The baseline empty request size was extracted from the saved final-run
    request after replacing only `current_facts` with []; the byte delta is
    calculated from the exact compact UTF-8 JSON serialization used by the
    frozen request-size helper.
    """
    empty_payload = json.dumps({"current_facts": []}, ensure_ascii=False, separators=(",", ":"))
    empty_shell = {"messages": [{"content": empty_payload}]}
    empty_shell_bytes = len(
        json.dumps(empty_shell, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    )

    def size_for(facts):
        payload = json.dumps(
            {"current_facts": [to_dict(fact) for fact in facts]},
            ensure_ascii=False,
            separators=(",", ":"),
        )
        shell = {"messages": [{"content": payload}]}
        return empty_request_bytes + request_bytes(shell) - empty_shell_bytes

    return size_for


@pytest.mark.parametrize(("incident_id", "empty_request_bytes"), CASES)
def test_selection_matches_frozen_decision_ids_and_metadata(incident_id, empty_request_bytes):
    facts, expected = _load_selection_case(incident_id)
    size_for = _request_size_for(empty_request_bytes)

    result = select_facts(facts, request_size_for=size_for)

    assert result.full_fact_count == expected["full_fact_count"]
    assert result.selected_fact_count == expected["selected_fact_count"]
    assert result.selector_used is expected["selector_used"]
    assert list(result.selected_ids) == expected["selected_ids"]
    assert list(result.omitted_ids) == expected["omitted_ids"]
    assert dict(result.selection_reasons) == expected["selection_reasons"]
    assert result.full_request_bytes == expected["full_request_bytes"]
    assert result.selected_request_bytes == expected["selected_request_bytes"]
    assert result.selected_fact_bytes == expected.get("selected_fact_bytes")


def test_application_failure_selection_is_the_exact_frozen_25_fact_sequence():
    facts, expected = _load_selection_case("application-failure-01")
    result = select_facts(facts, request_size_for=_request_size_for(8082))

    assert list(result.selected_ids) == [
        "F22", "F23", "F24", "F25", "F35", "F36", "F37", "F38", "F39",
        "F46", "F48", "F49", "F29", "F30", "F31", "F32", "F33", "F34",
        "F21", "F50", "F51", "F52", "F1", "F2", "F3",
    ]
    assert len(result.facts) == 25
    assert [to_dict(fact) for fact in result.facts] == expected["selected_facts"]
    assert all(
        selected is next(source for source in facts if source.fact_id == selected.fact_id)
        for selected in result.facts
    )


@pytest.mark.parametrize(("incident_id", "empty_request_bytes"), CASES)
def test_selector_is_repeatable_and_does_not_mutate_source_facts(incident_id, empty_request_bytes):
    facts, _ = _load_selection_case(incident_id)
    original_rows = tuple(to_dict(fact) for fact in facts)
    size_for = _request_size_for(empty_request_bytes)

    first = select_facts(facts, request_size_for=size_for)
    second = select_facts(facts, request_size_for=size_for)

    assert tuple(to_dict(fact) for fact in facts) == original_rows
    assert first == second
    assert all(any(selected is original for original in facts) for selected in first.facts)


def test_request_bytes_uses_compact_utf8_json():
    request = {"text": "failed — café", "values": [1, 2]}

    assert request_bytes(request) == len(
        json.dumps(request, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    )


def test_duplicate_fact_ids_are_rejected_before_selection():
    facts, _ = _load_selection_case("missing-secret-01")
    duplicated = (facts[0], facts[0])

    with pytest.raises(ValueError, match="Duplicate Fact IDs"):
        select_facts(duplicated, request_size_for=_request_size_for(9186))
