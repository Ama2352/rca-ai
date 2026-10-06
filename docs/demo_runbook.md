# RCA Demo v1 runbook

## Requirements and setup

- Python 3.10 or newer.
- A Groq API credential available as the process environment variable GROQ_API_KEY for live runs.
- Network access to Groq for live inference.

From the repository root:

~~~powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[test]"
~~~

Set GROQ_API_KEY using the environment/secret mechanism appropriate for your machine. The application reads the process environment; it does not load .env files. Never place a real key in .env.example, source, tests, or committed artifacts.

## Run a scenario

Run one scenario:

~~~powershell
python scripts/run_prepared_demo.py --scenario missing-secret-01
python scripts/run_prepared_demo.py --scenario application-failure-01
python scripts/run_prepared_demo.py --scenario ad-high-cpu-01
~~~

Run all three sequentially (the default):

~~~powershell
python scripts/run_prepared_demo.py --scenario all
~~~

Each run loads tests/fixtures/prepared_demo/<scenario>.json, builds and verifies Facts, retrieves H/K, and invokes the prepared-demo pipeline. It does not call the telemetry Processor or Fact Selector. A complete JSON summary, including final RCA results and provider usage, is printed to standard output. A failure is reported to standard error with a nonzero exit code; the runner stops at the first failed scenario.

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

Tests use fake providers and do not require GROQ_API_KEY.

## Troubleshooting

- Missing GROQ_API_KEY: configure the variable in the invoking shell/secret store; the runner exits before creating a provider pipeline.
- Budget error: the complete request exceeds the configured estimate. No evidence was silently removed; review the prepared input through the curation process rather than editing it at runtime.
- HTTP 400 other than json_validate_failed: no recovery retry is made.
- Repeated json_validate_failed: one identical retry is the maximum; inspect the structured provider error and stop rather than rerunning automatically.
- HTTP 429/5xx or transport failure: the existing provider retry policy is bounded. Optional pacing can reduce call frequency but cannot assure quota availability.
- Qualified result: read its Validator qualifications and unresolved items. A qualified hypothesis is not a confirmed root cause.

The prepared inputs are reviewed demo fixtures, not an arbitrary telemetry ingestion interface.
