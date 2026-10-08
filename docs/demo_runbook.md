# RCA Demo v1 runbook

## Requirements and setup

- Python 3.10 or newer.
- Groq and Cerebras API credentials available as process environment variables `GROQ_API_KEY` and `CEREBRAS_API_KEY` for live runs.
- Network access to Groq and Cerebras for live inference.

From the repository root:

~~~powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[test]"
~~~

The prepared Demo v1 default uses Groq for Generator and Cerebras for Validator. Set both credentials in the shell that starts the backend. The application reads process environment variables; it does not load `.env` files. Never place a real key in source, tests, or committed artifacts.

On the authorized development machine, load the existing local secrets in PowerShell without displaying them:

~~~powershell
$env:GROQ_API_KEY = (Get-Content -Raw 'D:\Dev\SideProjects\rca-ai\otel_demo_dataset\.secrets\groq-api-key.txt').Trim()
$env:CEREBRAS_API_KEY = (Get-Content -Raw 'D:\Dev\SideProjects\rca-ai\otel_demo_dataset\.secrets\cerebras-api-key.txt').Trim()
~~~

Keep these variables in the same PowerShell session used to start Uvicorn; the backend inherits that session's environment. Do not paste or print the values.

## Run a scenario

Run one scenario:

~~~powershell
python scripts/run_prepared_demo.py --scenario missing-secret-01
python scripts/run_prepared_demo.py --scenario application-failure-01
python scripts/run_prepared_demo.py --scenario ad-high-cpu-01
python scripts/run_prepared_demo.py --scenario dependency-unavailable-01
python scripts/run_prepared_demo.py --scenario messaging-failure-01
~~~

Run all five sequentially (the default):

~~~powershell
python scripts/run_prepared_demo.py --scenario all
~~~

Each run loads data/demo/<scenario>.json, builds and verifies Facts, retrieves H/K, and invokes the prepared-demo pipeline. It does not call the telemetry Processor or Fact Selector. A complete JSON summary, including final RCA results and provider usage, is printed to standard output. A failure is reported to standard error with a nonzero exit code; the runner stops at the first failed scenario.

To save console output locally, redirect it to the ignored artifacts/ directory. Do not commit raw provider outputs without reviewing them for sensitive data.

## Optional pacing

Provider pacing is disabled by default. Enable the shared provider-boundary pacer explicitly:

~~~powershell
python scripts/run_prepared_demo.py --scenario all --enable-pacing --pacing-delay-seconds 75
~~~

The pacer honors a usable Retry-After or rate-limit reset header; otherwise it waits the configured fallback. Pacing is applied between Generator and Validator calls, including a prepared-demo recovery attempt. It does not guarantee that quota limits will not be reached. GroqProvider's own bounded 429/5xx and transport retry behavior remains active.

## Request budget and recovery

Every complete Generator and Validator request is checked before transport. The default limit is 7,000 estimated tokens using ceil(serialized UTF-8 request bytes / 4). This is a local estimate, not Groq tokenization or a quota guarantee. An oversized request fails; the runner does not truncate Facts.

For the prepared-demo Validator only, a structured HTTP 400 with error.type=invalid_request_error and error.code=json_validate_failed permits one retry of the identical request. No malformed response is repaired or accepted. Other provider and contract errors fail closed. The default RCAPipeline.run() does not use this recovery wrapper.

## Offline tests

~~~powershell
python -m pytest -q -p no:cacheprovider tests/integration/pipeline/test_prepared_demo.py tests/unit/pipeline/test_prepared_demo_provider_wrappers.py tests/unit/pipeline/test_request_budget.py tests/unit/test_prepared_demo_runner.py
python -m pytest -q -p no:cacheprovider
~~~

Tests use fake providers and do not require provider credentials.

## Troubleshooting

- Missing GROQ_API_KEY or CEREBRAS_API_KEY: configure both in the invoking shell/secret store; the runner exits before creating a provider pipeline.
- Budget error: the complete request exceeds the configured estimate. No evidence was silently removed; review the prepared input through the curation process rather than editing it at runtime.
- HTTP 400 other than json_validate_failed: no recovery retry is made.
- Repeated json_validate_failed: one identical retry is the maximum; inspect the structured provider error and stop rather than rerunning automatically.
- HTTP 429/5xx or transport failure: the existing provider retry policy is bounded. Optional pacing can reduce call frequency but cannot assure quota availability.
- Qualified result: read its Validator qualifications and unresolved items. A qualified hypothesis is not a confirmed root cause.

The prepared inputs are reviewed demo fixtures, not an arbitrary telemetry ingestion interface.

## Full-stack interface

From the repository root, install the optional API dependencies and the frontend packages:

~~~powershell
python -m pip install -e ".[api,test]"
cd frontend
npm install
cd ..
~~~

In the backend terminal, first run the two secure PowerShell assignments above, then start the backend:

~~~powershell
python -m uvicorn rca_ai.api.demo:app --host 127.0.0.1 --port 8000
~~~

In a second terminal start the frontend:

~~~powershell
cd frontend
npm run dev
~~~

If the backend uses a non-default port, set `RCA_DEMO_API_TARGET` in the frontend terminal before `npm run dev`, for example `$env:RCA_DEMO_API_TARGET = 'http://127.0.0.1:8010'`.

Open the local Vite URL printed in the second terminal. Select a prepared incident and read its Scenario Overview before choosing **Analyze incident**. The overview uses the prepared fixture and static presentation copy; it does not contact Groq. Analysis can take several sequential provider calls, so the UI shows elapsed time and polls the in-memory job. A backend failure appears as an execution error, not an RCA abstention. Switching incidents clears the prior result. Qualifications and unresolved questions remain visible on retained hypotheses.

The API provides `GET /api/demo/incidents`, `POST /api/demo/analyses` with `{"incident_id":"missing-secret-01"}`, and `GET /api/demo/analyses/{analysis_id}`. It accepts only the three tracked prepared incidents, runs one job at a time, and forgets jobs on restart. The browser demo does not add a proactive 75-second wait. Groq's bounded transport retries for retryable rate-limit/server/transport failures remain active; if a final HTTP 429 is exhausted, the API reports `RATE_LIMITED`, returns `Retry-After` when available, and the UI enables one manual retry after that delay. Both API keys stay server-side. The execution audit reports Groq / `openai/gpt-oss-120b` for Generator and Cerebras / `gpt-oss-120b` for Validator. For a deployment, route `/api` to the FastAPI service; Vite's proxy is development-only.

Offline integration checks use fake providers:

~~~powershell
python -m pytest -q -p no:cacheprovider tests/integration/api/test_demo_api.py
cd frontend
npm run typecheck
npm run lint
npm run test
~~~
