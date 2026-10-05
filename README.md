# RCA AI demo

RCA AI turns normalized incident evidence into source-backed candidate explanations for investigation. This repository is the clean home for the validated demo architecture. Phase 0 contains only the Python package skeleton and migration documentation; the RCA implementation has **not** been ported.

The demo input boundary is **Normalized Incident Evidence**. Raw telemetry collection, Prometheus/OpenSearch/Jaeger/Kubernetes connectors, and Source Adapters remain outside this project’s demo scope.

The frozen in-scope flow is deterministic Fact View construction, optional deterministic Fact selection, History and Domain Knowledge retrieval, an LLM Hypothesis Generator, an LLM Hypothesis Validator, and deterministic result assembly for an API/UI. Current Facts, historical precedent, general knowledge, and generated inference keep separate provenance. See [architecture](docs/architecture.md), [provenance](docs/provenance.md), and the [migration inventory](docs/migration_inventory.md).

## Layout and status

- `src/rca_ai/`: installable package; no RCA implementation modules yet.
- `tests/`: unit, integration, and fixture locations.
- `data/`: future demo inputs, History corpus, and Domain Knowledge corpus.
- `docs/`: frozen decisions, provenance, limitations, and migration sources.
- `scripts/`: future project utilities.

The old research workspaces are read-only references. Phase 1 must be reviewed against `docs/migration_inventory.md` before any behavior is ported.

## Local setup

Use Python 3.10 or newer. From this directory:

```powershell
python -m pip install -e .
python -c "import rca_ai; print('rca_ai import OK')"
python -m pip install -e ".[test]"  # Only when running tests
python -m pytest tests
```

The Groq credential variable name is shown in `.env.example`; never commit a real key. No provider call is made by the Phase 0 package.

## Code documentation rule

Comments and docstrings should explain **why** significant behavior exists, particularly architectural invariants. Important future modules should state their responsibility, inputs/outputs, invariants, and why those invariants protect source fidelity. Do not comment obvious syntax or loops. For example, the future Fact builder should explain why it must not summarize or infer causality: semantic inference belongs to the Hypothesis layer.
