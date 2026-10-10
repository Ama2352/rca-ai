# RCA AI — Prepared RCA Demo v1

RCA Demo v1 runs a frozen, evidence-grounded reasoning pipeline against nine prepared incident inputs. Seven scenarios are verified; `crash-loop-backoff-01` and `downstream-latency-01` are runnable but remain experimental. It produces candidate explanations for investigation; it does not guarantee a confirmed root-cause diagnosis.

The existing React interface loads a nine-scenario catalog from a lightweight FastAPI service. All nine fixture- and manifest-validated scenarios are available to analyze. Readiness remains separate: seven are verified, while the two experimental scenarios retain visible limitations and may fail validation. Each runnable scenario has a pre-analysis overview; analysis runs in one in-process worker and the interface polls for the assembled result. Merely opening the overview makes no provider call.

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

The official `RCAPipeline` builds and verifies every Fact, retrieves History and Knowledge, then passes the complete Fact set to the Generator and each Validator call. A complete-request guard rejects oversized requests rather than truncating or reducing evidence.

See the [architecture](docs/architecture.md), [demo runbook](docs/demo_runbook.md), [verification record](docs/verification.md), and the [RCA contract](docs/rca_contract.md). The telemetry and [provenance](docs/provenance.md) contracts document the upstream research boundary; raw telemetry collection is not part of the prepared-demo run.

## Quick start

### Docker Compose

Create an untracked `.env` from `.env.example` and set `GROQ_API_KEY` and
`CEREBRAS_API_KEY` for live analysis. Then run from the repository root:

```sh
docker compose up --build
```

Open <http://localhost:3000>. Vite serves the frontend and proxies `/api`
requests to FastAPI. The backend is also available at <http://localhost:8000>
(for example, `/api/demo/incidents`). Source changes are mounted into the
containers for local development. Set `FRONTEND_PORT` or `BACKEND_PORT` in
`.env` if either host port is occupied. The catalog loads without provider
keys; starting an analysis requires both keys. Stop the stack with
`docker compose down`.

### Local development

Use Python 3.10 or newer. From the repository root:

```powershell
python -m pip install -e .
python scripts/run_prepared_demo.py --scenario missing-secret-01
```

Configure `GROQ_API_KEY` and `CEREBRAS_API_KEY` in the backend environment before running the live demo; do not place credentials in tracked files. To run all nine scenarios sequentially:

```powershell
python scripts/run_prepared_demo.py --scenario all
```

Provider calls use Groq’s bounded transport retries. The prepared pipeline adds no pacing or automatic Validator retry. See the [runbook](docs/demo_runbook.md) for test commands and troubleshooting.

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

Open the URL printed by Vite. Its development proxy forwards `/api` to the local FastAPI service. Configure both `GROQ_API_KEY` and `CEREBRAS_API_KEY` in the API process only before invoking analysis. See the [runbook](docs/demo_runbook.md) for behavior and limitations.

## Repository map

- `src/rca_ai/`: frozen domain, Fact construction, retrieval, reasoning, provider, and pipeline components.
- `data/demo/`: version-controlled prepared evidence inputs and their curation manifest, including the two experimental inputs available for analysis.
- `data/history/` and `data/knowledge/`: frozen H/K stores.
- `scripts/run_prepared_demo.py`: standalone prepared-demo entry point.
- `src/rca_ai/api/`: three-route FastAPI boundary with volatile analysis jobs.
- `frontend/`: React scenario overview and live RCA result viewer.
- `tests/`: deterministic regression suite using offline providers.

Seven prepared inputs are verified; the two experimental inputs are runnable but may fail validation or produce limited hypotheses. The demo does not claim arbitrary telemetry ingestion, production readiness, or that retrieved H/K context proves a current incident fact.
