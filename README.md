# RCA AI — Prepared RCA Demo v1

RCA Demo v1 runs a frozen, evidence-grounded reasoning pipeline against three reviewed prepared incident inputs: `missing-secret-01`, `application-failure-01`, and `ad-high-cpu-01`. It produces candidate explanations for investigation; it does not guarantee a confirmed root-cause diagnosis.

## Architecture

```text
Prepared Canonical Evidence
  → deterministic Fact Builder / Verification
  → History and Knowledge Retrieval
  → Generator
  → Validator
  → deterministic Assembler
  → RCAResult
```

The prepared-demo path passes every generated Fact to the Generator and Validator without invoking the Fact Selector. A complete-request guard rejects an oversized Generator or Validator request rather than truncating evidence. The default `RCAPipeline.run()` remains the separate Selector-backed path.

See the [architecture](docs/architecture.md), [demo runbook](docs/demo_runbook.md), [verification record](docs/verification.md), and the [RCA contract](docs/rca_contract.md). The telemetry and [provenance](docs/provenance.md) contracts document the upstream research boundary; raw telemetry collection is not part of the prepared-demo run.

## Quick start

Use Python 3.10 or newer. From the repository root:

```powershell
python -m pip install -e .
python scripts/run_prepared_demo.py --scenario missing-secret-01
```

Configure `GROQ_API_KEY` in the invoking environment before running the live demo; do not place credentials in tracked files. To run all three scenarios sequentially:

```powershell
python scripts/run_prepared_demo.py --scenario all
```

Optional provider pacing is disabled by default. See the [runbook](docs/demo_runbook.md) for `--enable-pacing`, test commands, and troubleshooting.

## Repository map

- `src/rca_ai/`: frozen domain, Fact construction, retrieval, reasoning, provider, and pipeline components.
- `tests/fixtures/prepared_demo/`: the three version-controlled prepared evidence inputs and selection manifest.
- `data/history/` and `data/knowledge/`: frozen H/K stores.
- `scripts/run_prepared_demo.py`: standalone prepared-demo entry point.
- `tests/`: deterministic regression suite using offline providers.

The demo is verified for these three prepared inputs only. It does not claim arbitrary telemetry ingestion, production readiness, or that retrieved H/K context proves a current incident fact.
