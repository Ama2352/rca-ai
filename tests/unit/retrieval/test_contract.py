from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

import pytest

from rca_ai.domain.models import HistoricalContext, KnowledgeItem
from rca_ai.retrieval.history import load_history_store, retrieve_history
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
    actual_hash = hashlib.sha256(corpus_path.read_bytes()).hexdigest()
    assert actual_hash == "1b2052bb17eeae39a1e1dbc2dd5c7ed8d599dc15efeb59445e6de1d25c1ca167"
    assert manifest["corpus_sha256"] == actual_hash

    raw_order = [json.loads(line)["incident_id"] for line in corpus_path.read_text(encoding="utf-8").splitlines() if line]
    raw_records = tuple(json.loads(line) for line in corpus_path.read_text(encoding="utf-8").splitlines() if line)
    loaded = load_history_store(corpus_path)
    assert [row["incident_id"] for row in loaded] == raw_order
    assert loaded == raw_records
    assert len(loaded) == 22


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


def test_plain_bm25_history_uses_exact_query_and_frozen_scores():
    query = (FIXTURES / "inputs" / "plain-query.txt").read_text(encoding="utf-8")
    expected = _json(FIXTURES / "expected" / "retrieval-03.json")
    result = retrieve_history(query)
    assert result.strategy == "plain_bm25"
    assert result.query == expected["history"]["query"]
    assert [item.source_id for item in result.items] == expected["history_ids"]
    assert result.metadata["ranked"] == [
        {"rank": rank, "incident_id": row[0], "bm25_score": row[1]}
        for rank, row in enumerate(expected["history"]["ranked"], 1)
    ]
    assert all(isinstance(item, HistoricalContext) for item in result.items)
    assert all(item.source_id == item.record["incident_id"] for item in result.items)
    assert all("retrieval_rank" not in item.record and "bm25_score" not in item.record for item in result.items)
    source_by_id = {row["incident_id"]: row for row in load_history_store()}
    record_fields = ("incident_id", "affected_component", "retrieval_text", "root_cause", "recommended_action", "resolution_note")
    assert all(item.record == {key: source_by_id[item.source_id][key] for key in record_fields if key in source_by_id[item.source_id]} for item in result.items)
    assert retrieve_history(query) == result


def test_history_store_reads_do_not_mutate_loaded_records():
    loaded = load_history_store(HISTORY / "historical_incidents.jsonl")
    before = copy.deepcopy(loaded)
    retrieve_history("ad CPU utilization increased")
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
        ("plain-query.txt", "retrieval-03.json"),
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


def test_weakly_relevant_positive_knowledge_is_not_semantically_filtered():
    payload = _json(FIXTURES / "inputs" / "channel-incident-01.json")
    result = retrieve_knowledge(payload)
    assert "kubernetes.secret.required_startup" in [item.source_id for item in result.items]
