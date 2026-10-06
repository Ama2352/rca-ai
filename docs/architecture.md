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

The canonical prepared fixtures live in `tests/fixtures/prepared_demo/`. The supported command is `scripts/run_prepared_demo.py`; it loads one scenario or all three, then delegates stage behavior to `PreparedDemoPipeline`.

## Evidence and retrieval

The Fact Builder deterministically projects each canonical observation into one source-linked Fact. The prepared pipeline independently verifies that projection before reasoning. Every generated Fact is passed unchanged to both Generator and Validator; the Fact Selector is not invoked in this path.

History and Domain Knowledge are retrieved from the Core's deterministic retrieval projection. H is precedent and K is general operational knowledge; neither becomes current incident evidence. The Validator's current-F evidence references are checked against the supplied Facts, and the Assembler resolves references without rewriting the validated hypothesis.

## Provider boundary

`BudgetGuardProvider` checks the complete serialized request before each Generator or Validator provider call. The default limit is 7,000 estimated input tokens, computed as `ceil(UTF-8 request bytes / 4)`. This is an internal estimate, not the provider tokenizer or a quota guarantee. Oversized requests fail explicitly; no Fact is truncated or selected away.

The prepared-demo Validator wrapper retries at most once, with the identical request, only for HTTP 400 where the structured provider error has `type=invalid_request_error` and `code=json_validate_failed`. All other failures propagate. The default `RCAPipeline.run()` does not use this recovery wrapper.

The existing Groq provider retains its bounded 429/5xx and transport retry behavior. Optional `ProviderCallPacer` wraps the shared provider boundary; it is disabled by default and, when enabled, uses response retry/reset headers where available or the configured fallback delay. Pacing does not guarantee quota availability.

## Pipeline separation

- `PreparedDemoPipeline` is the reviewed prepared-fixture path: all Facts, no Fact Selector, complete per-call budget guard, optional pacing, and prepared-only Validator recovery.
- `RCAPipeline.run()` remains the default Selector-backed pipeline and retains its existing semantics.
- The telemetry Processor and source connectors are separate upstream research/prototype work. They are not dependencies of the prepared-demo runner.

The Validator can retain a useful hypothesis as `KEEP_QUALIFIED` while naming unsupported assumptions, uncertainty, or contradictions. A qualified candidate is still a hypothesis—not a confirmed root cause. See the [RCA contract](rca_contract.md), [runbook](demo_runbook.md), and [verification record](verification.md).
