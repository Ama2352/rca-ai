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

The prepared demo inputs live in `data/demo/`. The supported command is `scripts/run_prepared_demo.py`; it loads one scenario or all nine fixture- and manifest-validated inputs, then invokes the official `RCAPipeline`. Readiness is a separate quality label: seven inputs are demo-ready and Crash Loop Backoff / Downstream Latency remain experimental. Their analyses use the same schema and evidence-reference validation and may return a visible execution failure.

## Full-stack demo boundary

The React frontend calls `GET /api/demo/incidents` for scenario registry metadata, available signal names, and an evidence-backed incident snapshot. Human-facing titles, descriptions, known causes, symptoms, and investigation summaries live in the frontend static map and do not enter the RCA input. Catalog loading never creates a provider request.

`POST /api/demo/analyses` accepts only a prepared scenario ID and returns a job ID. One in-process worker invokes `RCAPipeline`; `GET /api/demo/analyses/{analysis_id}` exposes queued/running/completed/failed state. On completion it returns the assembled `RCAResult`, original Facts, and candidate-specific F/H/K source resolution keyed by hypothesis ID. Backend errors are distinct from an empty-candidate RCA abstention. The UI polls, retains the Scenario Overview, and discards stale responses after incident switches.

Jobs exist only in memory; restarting the API loses them. Concurrent submissions receive HTTP 409. The Vite development proxy handles same-origin `/api` calls locally. The production Caddy container serves the React app over HTTPS and routes the allowlisted `/api` endpoints to the private FastAPI container. Analysis uses the official Core pipeline. See [the AWS deployment guide](deployment/manual-setup.md) for the single-EC2 setup.

## Evidence and retrieval

The Fact Builder deterministically projects each canonical observation into one source-linked Fact. `RCAPipeline` verifies that projection before reasoning. Every generated Fact is passed unchanged to the Generator and each independent Validator call.

History and Domain Knowledge are retrieved from the Core's deterministic retrieval projection. H is precedent and K is general operational knowledge; neither becomes current incident evidence. The Validator's current-F evidence references are checked against the supplied Facts, and the Assembler resolves references without rewriting the validated hypothesis.

## Provider boundary

`BudgetGuardProvider` checks the complete serialized request before each Generator or Validator provider call. The default limit is 7,000 estimated input tokens, computed as `ceil(UTF-8 request bytes / 4)`. This is an internal estimate, not the provider tokenizer or a quota guarantee. Oversized requests fail explicitly before transport; the guard never changes the request.

The existing Groq provider retains its bounded 429/5xx and transport retry behavior. No additional pacing or Validator retry is applied by the Core pipeline.

The prepared Demo v1 default routes Generator to Groq `openai/gpt-oss-120b` and Validator to Cerebras `gpt-oss-120b`. Cerebras uses its existing one-attempt transport adapter; it does not add automatic fallback or retries. Exhausted HTTP 429 errors from either provider are returned as `RATE_LIMITED` for a manual user retry. The execution audit reports the configured provider/model pair separately from measured stage durations.

## Official pipeline

- `RCAPipeline` is the only supported Core orchestration path: it builds and verifies all Facts, retrieves H/K, generates once, validates each hypothesis independently, and assembles deterministically.
- `BudgetGuardProvider` measures each complete request and fails visibly when it exceeds the configured estimate.
- The telemetry Processor and source connectors are separate upstream research/prototype work. They are not dependencies of the prepared-demo runner.

The Validator can retain a useful hypothesis as `KEEP_QUALIFIED` while naming unsupported assumptions, uncertainty, or contradictions. A qualified candidate is still a hypothesis—not a confirmed root cause. See the [RCA contract](rca_contract.md), [runbook](demo_runbook.md), and [verification record](verification.md).
