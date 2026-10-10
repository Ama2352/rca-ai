from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

import pytest

from rca_ai.domain.models import HistoricalContext, KnowledgeItem
from rca_ai.retrieval.history import _canonical_history_bytes, load_history_store, retrieve_history
from rca_ai.retrieval.knowledge import load_knowledge_store, retrieve_knowledge


PROJECT_ROOT = Path(__file__).resolve().parents[3]
FIXTURES = PROJECT_ROOT / "tests" / "fixtures" / "retrieval"
HISTORY = PROJECT_ROOT / "data" / "history"
KNOWLEDGE = PROJECT_ROOT / "data" / "knowledge" / "knowledge.json"


def _json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def test_history_store_hash_order_and_source_identity_are_frozen():
    corpus_path = HISTORY / "historical_incidents.jsonl"
    manifest = _json(HISTORY / "corpus_freeze_manifest.json")
    actual_hash = hashlib.sha256(_canonical_history_bytes(corpus_path.read_bytes())).hexdigest()
    assert actual_hash == "1b2052bb17eeae39a1e1dbc2dd5c7ed8d599dc15efeb59445e6de1d25c1ca167"
    assert manifest["corpus_sha256"] == actual_hash

    raw_order = [json.loads(line)["incident_id"] for line in corpus_path.read_text(encoding="utf-8").splitlines() if line]
    raw_records = tuple(json.loads(line) for line in corpus_path.read_text(encoding="utf-8").splitlines() if line)
    loaded = load_history_store(corpus_path)
    assert [row["incident_id"] for row in loaded] == raw_order
    assert loaded == raw_records
    assert len(loaded) == 22


def test_history_freeze_hash_is_line_ending_independent_and_still_checks_content(tmp_path):
    source = HISTORY / "historical_incidents.jsonl"
    raw = source.read_bytes()
    manifest = (HISTORY / "corpus_freeze_manifest.json").read_bytes()

    for name, line_ending_variant in (
        ("lf", raw),
        ("crlf", raw.replace(b"\n", b"\r\n")),
    ):
        history_dir = tmp_path / name
        history_dir.mkdir()
        corpus_path = history_dir / "historical_incidents.jsonl"
        corpus_path.write_bytes(line_ending_variant)
        (history_dir / "corpus_freeze_manifest.json").write_bytes(manifest)
        assert load_history_store(corpus_path) == load_history_store(source)

    tampered_dir = tmp_path / "tampered"
    tampered_dir.mkdir()
    tampered_path = tampered_dir / "historical_incidents.jsonl"
    tampered_path.write_bytes(raw + b" ")
    (tampered_dir / "corpus_freeze_manifest.json").write_bytes(manifest)
    with pytest.raises(ValueError, match="does not match its freeze manifest"):
        load_history_store(tampered_path)


def test_history_retrieval_reconstructs_channel_queries_and_frozen_rankings():
    cases = (
        ("channel-incident-01.json", "retrieval-01.json"),
        ("channel-incident-02.json", "retrieval-02.json"),
    )
    for fixture, expected_file in cases:
        payload = _json(FIXTURES / "inputs" / fixture)
        expected = _json(FIXTURES / "expected" / expected_file)
        before = copy.deepcopy(payload)
        result = retrieve_history(payload)
        assert result.strategy == "channel_bm25_rrf"
        assert result.query == expected["history"]["query"]
        assert [item.source_id for item in result.items] == expected["history_ids"]
        assert result.metadata["diagnostics"] == expected["history"]["diagnostics"]
        assert all(isinstance(item, HistoricalContext) for item in result.items)
        assert [item.alias for item in result.items] == ["H1", "H2", "H3"]
        assert all(item.source_id == item.record["incident_id"] for item in result.items)
        assert payload == before
        assert retrieve_history(payload) == result


def test_history_store_reads_do_not_mutate_loaded_records():
    loaded = load_history_store(HISTORY / "historical_incidents.jsonl")
    before = copy.deepcopy(loaded)
    payload = _json(FIXTURES / "inputs" / "channel-incident-01.json")
    retrieve_history(payload)
    assert loaded == before


def test_knowledge_store_hash_and_source_records_are_preserved():
    raw = KNOWLEDGE.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == "c1e806eda30b5d78b10896bc8a68690b2a409094a2a5b8c3f86f84bdfbd11890"
    records = load_knowledge_store(KNOWLEDGE)
    assert len(records) == len(_json(KNOWLEDGE))
    assert records == tuple(_json(KNOWLEDGE))


@pytest.mark.parametrize(
    ("fixture_name", "expected_name"),
    (
        ("channel-incident-01.json", "retrieval-01.json"),
        ("channel-incident-02.json", "retrieval-02.json"),
    ),
)
def test_knowledge_retrieval_matches_frozen_query_order_scores_and_aliases(fixture_name, expected_name):
    fixture = FIXTURES / "inputs" / fixture_name
    retrieval_input = fixture.read_text(encoding="utf-8") if fixture.suffix == ".txt" else _json(fixture)
    expected = _json(FIXTURES / "expected" / expected_name)
    result = retrieve_knowledge(retrieval_input)
    expected_ranking = expected["domain_knowledge"]["ranked"]
    expected_rows = [(key, score) for key, score in expected_ranking if score > 0]

    assert result.query == expected["domain_knowledge"]["query"]
    assert [item.source_id for item in result.items] == [key for key, _ in expected_rows]
    assert [item.alias for item in result.items] == [f"K{i}" for i in range(1, len(expected_rows) + 1)]
    assert list(result.ranking) == [tuple(row) for row in expected_ranking]
    assert len(result.items) <= 3
    assert all(isinstance(item, KnowledgeItem) for item in result.items)
    source_by_id = {row["knowledge_key"]: row for row in load_knowledge_store()}
    assert all(item.record == source_by_id[item.source_id] for item in result.items)
    assert retrieve_knowledge(retrieval_input) == result


def test_legacy_plain_query_fixture_is_not_a_runtime_input():
    plain_query = (FIXTURES / "inputs" / "plain-query.txt").read_text(encoding="utf-8")
    with pytest.raises(TypeError, match="structured mapping"):
        retrieve_history(plain_query)
    with pytest.raises(TypeError, match="structured mapping"):
        retrieve_knowledge(plain_query)


def test_history_runtime_has_no_plain_retrieval_implementation_or_type_dispatch():
    source = (PROJECT_ROOT / "src" / "rca_ai" / "retrieval" / "history.py").read_text(encoding="utf-8")
    assert "_plain_retrieval" not in source
    assert "isinstance(retrieval_input, str)" not in source


def test_weakly_relevant_positive_knowledge_is_not_semantically_filtered():
    payload = _json(FIXTURES / "inputs" / "channel-incident-01.json")
    result = retrieve_knowledge(payload)
    assert "kubernetes.secret.required_startup" in [item.source_id for item in result.items]
