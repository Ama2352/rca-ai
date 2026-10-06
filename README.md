# RCA AI demo

RCA AI turns canonical, source-linked incident observations into candidate explanations for investigation. The clean Python project contains the frozen reasoning core and an explicit Processor-to-Core evidence boundary.

The Core input is `IncidentInput(incident_id, evidence)`, where `evidence` is `CanonicalIncidentEvidence` produced by the telemetry Processor. Raw telemetry connectors are upstream research/prototype work; the clean Core does not query Prometheus, OpenSearch, Jaeger, or Kubernetes directly.

The Processor reports source-faithful observations and provenance. The Core builds one Fact per observation and independently creates retrieval material; it owns search eligibility and Fact selection. History, Domain Knowledge, current Facts, generated Hypotheses, and Validator Qualifications remain distinct. See the [architecture](docs/architecture.md), [telemetry contract](docs/telemetry_contract.md), [RCA contract](docs/rca_contract.md), and [migration inventory](docs/migration_inventory.md).

The release runner currently uses the Processor's canonical entry point with its existing modality selection. The broader structural-only Processor path remains an experiment and has not yet been integrated into live release regression. The deterministic Fact Selector bounds request size but can omit most observations in high-volume cases; selected Facts are not a coverage guarantee.

## Layout and status

- `src/rca_ai/domain/`: canonical evidence and RCA semantic contracts.
- `src/rca_ai/facts/` and `retrieval/`: deterministic Core projections and unchanged retrieval engines.
- `src/rca_ai/reasoning/`, `providers/`, and `pipeline/`: frozen Generator, Validator, provider boundary, orchestration, and assembler.
- `tests/`: unit/integration regressions; `data/`: frozen H/K stores.
- `docs/`: contracts, decisions, limitations, and migration lineage; `scripts/`: release runner.

Historical normalized-evidence and manually prepared retrieval inputs remain test controls only. They are not the new Processor/Core public contract.

## Local setup

Use Python 3.10 or newer. From this directory:

```powershell
python -m pip install -e .
python -c "import rca_ai; print('rca_ai import OK')"
python -m pip install -e ".[test]"  # Only when running tests
python -m pytest tests
```

The Groq credential variable name is shown in `.env.example`; never commit a real key. Unit and integration tests use local fake providers; live release regression requires an explicitly available `GROQ_API_KEY`.

## Code documentation rule

Comments and docstrings should explain **why** significant behavior exists, particularly architectural invariants. Important modules state their responsibility, inputs/outputs, and why invariants protect source fidelity. Do not comment obvious syntax or loops. The Fact builder does not summarize or infer causality because semantic inference belongs to the Hypothesis layer.
