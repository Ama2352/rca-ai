# RCA Demo v1 architecture

RCA Demo v1 runs reviewed, prepared canonical evidence. It does not invoke the telemetry Processor or acquire raw metrics, logs, traces, or Kubernetes objects at runtime.

~~~mermaid
flowchart TD
    A[Prepared Canonical Evidence]
    B[Fact Builder and Verification]
    C[History and Knowledge Retrieval]
    D[Generator]
    E[Validator]
    F[Deterministic Assembler]
    G[Final RCAResult]
    A --> B
    A --> C
    B --> D
    C --> D
    D --> E --> F --> G
~~~

The canonical prepared inputs live in `data/demo/`. The supported command is `scripts/run_prepared_demo.py`; it loads one scenario or all five demo-ready inputs, then delegates stage behavior to `PreparedDemoPipeline`.

## Full-stack demo boundary

The React frontend calls `GET /api/demo/incidents` for presentation-only scenario metadata. The API derives the available signal names from each prepared fixture, and its curated title, symptoms, and investigation focus do not enter the RCA input. Catalog loading never creates a provider request.

`POST /api/demo/analyses` accepts only a prepared scenario ID and returns a job ID. One in-process worker invokes the unchanged `PreparedDemoPipeline`; `GET /api/demo/analyses/{analysis_id}` exposes queued/running/completed/failed state. On completion it returns the assembled `RCAResult`, original Facts, and candidate-specific F/H/K source resolution keyed by hypothesis ID. Backend errors are distinct from an empty-candidate RCA abstention. The UI polls, retains the Scenario Overview, and discards stale responses after incident switches.

Jobs exist only in memory; restarting the API loses them. Concurrent submissions receive HTTP 409. The Vite development proxy handles same-origin `/api` calls locally; a deployment must route `/api` to the Python service. This layer does not change the default Selector-backed `RCAPipeline.run()`.

## Evidence and retrieval

The Fact Builder deterministically projects each canonical observation into one source-linked Fact. The prepared pipeline independently verifies that projection before reasoning. Every generated Fact is passed unchanged to both Generator and Validator; the Fact Selector is not invoked in this path.

History and Domain Knowledge are retrieved from the Core's deterministic retrieval projection. H is precedent and K is general operational knowledge; neither becomes current incident evidence. The Validator's current-F evidence references are checked against the supplied Facts, and the Assembler resolves references without rewriting the validated hypothesis.

## Provider boundary

`BudgetGuardProvider` checks the complete serialized request before each Generator or Validator provider call. The default limit is 7,000 estimated input tokens, computed as `ceil(UTF-8 request bytes / 4)`. This is an internal estimate, not the provider tokenizer or a quota guarantee. Oversized requests fail explicitly; no Fact is truncated or selected away.

The prepared-demo Validator wrapper retries at most once, with the identical request, only for HTTP 400 where the structured provider error has `type=invalid_request_error` and `code=json_validate_failed`. All other failures propagate. The default `RCAPipeline.run()` does not use this recovery wrapper.

The existing Groq provider retains its bounded 429/5xx and transport retry behavior. Optional `ProviderCallPacer` wraps the shared provider boundary; it is disabled by default and, when enabled, uses response retry/reset headers where available or the configured fallback delay. Pacing does not guarantee quota availability.

The prepared Demo v1 default routes Generator to Groq `openai/gpt-oss-120b` and Validator to Cerebras `gpt-oss-120b`. Cerebras uses its existing one-attempt transport adapter; it does not add automatic fallback or retries. Exhausted HTTP 429 errors from either provider are returned as `RATE_LIMITED` for a manual user retry. The execution audit reports the configured provider/model pair separately from measured stage durations.

## Pipeline separation

- `PreparedDemoPipeline` is the reviewed prepared-fixture path: all Facts, no Fact Selector, complete per-call budget guard, optional pacing, and prepared-only Validator recovery.
- `RCAPipeline.run()` remains the default Selector-backed pipeline and retains its existing semantics.
- The telemetry Processor and source connectors are separate upstream research/prototype work. They are not dependencies of the prepared-demo runner.

The Validator can retain a useful hypothesis as `KEEP_QUALIFIED` while naming unsupported assumptions, uncertainty, or contradictions. A qualified candidate is still a hypothesis—not a confirmed root cause. See the [RCA contract](rca_contract.md), [runbook](demo_runbook.md), and [verification record](verification.md).
