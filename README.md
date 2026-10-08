# RCA AI — Prepared RCA Demo v1

RCA Demo v1 runs a frozen, evidence-grounded reasoning pipeline against three reviewed prepared incident inputs: `missing-secret-01`, `application-failure-01`, and `ad-high-cpu-01`. It produces candidate explanations for investigation; it does not guarantee a confirmed root-cause diagnosis.

The existing React interface now loads a three-incident catalog from a lightweight FastAPI service. Each scenario has a pre-analysis overview; analysis runs in one in-process worker and the interface polls for the real assembled result. Merely opening the overview makes no provider call.

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

For the full-stack interface, install the API extra and frontend dependencies, then start the two local servers in separate terminals:

```powershell
python -m pip install -e ".[api]"
python -m uvicorn rca_ai.api.demo:app --host 127.0.0.1 --port 8000
```

```powershell
cd frontend
npm install
npm run dev
```

Open the URL printed by Vite. Its development proxy forwards `/api` to the local FastAPI service. Configure `GROQ_API_KEY` in the API process only before invoking analysis. See the [runbook](docs/demo_runbook.md) for behavior and limitations.

## Repository map

- `src/rca_ai/`: frozen domain, Fact construction, retrieval, reasoning, provider, and pipeline components.
- `data/demo/`: the three version-controlled prepared evidence inputs and their curation manifest.
- `data/history/` and `data/knowledge/`: frozen H/K stores.
- `scripts/run_prepared_demo.py`: standalone prepared-demo entry point.
- `src/rca_ai/api/`: three-route FastAPI boundary with volatile analysis jobs.
- `frontend/`: React scenario overview and live RCA result viewer.
- `tests/`: deterministic regression suite using offline providers.

The demo is verified for these three prepared inputs only. It does not claim arbitrary telemetry ingestion, production readiness, or that retrieved H/K context proves a current incident fact.
