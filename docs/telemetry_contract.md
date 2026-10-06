# Telemetry contract

This document describes the researched and prototyped observation path from raw operational telemetry to **Normalized Incident Evidence**. It is an upstream boundary description, not a claim that the clean RCA demo currently runs telemetry connectors.

## Scope and boundary

~~~mermaid
flowchart TD
    A[Raw telemetry sources]
    B[Connectors]
    C[Source Adapters]
    D[Deterministic evidence processing]
    E[Normalized Incident Evidence]
    A --> B --> C --> D --> E
~~~

The telemetry contract ends at **CanonicalIncidentEvidence** (the canonical form of Normalized Incident Evidence), the input boundary of the RCA core documented in the [RCA Contract](rca_contract.md). The clean runtime does not directly query Prometheus, OpenSearch, Jaeger, or Kubernetes.

Processor v1.1 currently exposes two relevant capture paths. The clean project's release runner and canonical capture test use `process_capture_canonical`, which applies the existing modality selection before projecting selected observations. The separate `process_capture_canonical_structural` path is an experiment that bypasses RCA-relevance eligibility/ranking/caps; it is not currently connected to that runner, and structural-only live E2E has not passed. The canonical contract itself carries no Processor-supplied RCA retrieval eligibility, but it does not imply that every raw or processed source record survives the selected capture path.

The research used `NormalizedTelemetry` for source-shaped input and `IncidentEvidence` for the Processor's modality-specific output. The current cross-layer contract is `CanonicalIncidentEvidence`, containing a window and ordered canonical observations. If an acquisition layer uses `IncidentTelemetryBundle` for transport, that bundle is upstream and is not itself the RCA input unless projected to this contract.

## Sources and responsibilities

| Source | Observations represented in the research |
|---|---|
| Prometheus | Metric series, labels, resource identity, samples, and deterministic before/after statistics. |
| OpenSearch | Log records and patterns, with service/scope/severity and occurrence or rate changes. |
| Jaeger | Spans, operations, service relationships, latency, and error observations. |
| Kubernetes | Pod/container state, waiting reason/message, workload/deployment data, and events when present in the capture. |

**Connector** and **Source Adapter** are different responsibilities:

- A Connector knows a source system's query/acquisition mechanism and retrieves its raw, source-specific payloads. Research captures include Prometheus, OpenSearch, Jaeger, and Kubernetes payloads; they do not establish production-grade connector coverage.
- A Source Adapter parses source-specific payload shapes and preserves record identity and location for later processing. In the telemetry prototype, source_adapters.py loaded captured payloads into canonical records such as metric series, log records, spans, pods, events, and deployments.
- Modality processors perform deterministic extraction, grouping, aggregation, ranking, and budgeted shaping within their evidence lane. They do not decide the incident's root cause.

## Information classes

~~~mermaid
flowchart LR
    A[Raw source signal] --> B[Observed]
    B --> C[Deterministically derived]
    D[Hypothesized cause] -. outside normalization .-> E[RCA Hypothesis layer]
~~~

- **Observed** means a source explicitly reported a value or state.
- **Derived** means a deterministic calculation over observations, such as a before/after difference, rate, or aggregate.
- **Hypothesized** means a semantic explanation of why observations occurred. It belongs in the RCA Hypothesis layer, not telemetry normalization.

Derived values should remain distinguishable from their source observations and should retain enough context to reproduce or audit the calculation. Missing modality data is missing coverage, not evidence that a system is healthy.

## Normalization and provenance

Normalization should preserve source meaning and identity while shaping records for downstream use. The research prototype normalized common volatile log tokens (for example UUIDs and long identifiers) for pattern grouping and retained example messages and source references. This is pattern-shaping, not a general PII/security-redaction guarantee; no universal sanitizer contract was demonstrated. Any source-specific redaction policy must be explicit and must not silently change evidence meaning.

Normalized observations should retain, where the source provides them:

- source system and source record/object identity;
- entity and modality;
- observed field/value and any deterministic comparison values;
- a source path or equivalent locator back to the captured payload.

Exact provenance fields varied by modality and prototype contract. Do not assume every source record supplies every item above.

## Canonical normalized output boundary

The Processor currently emits a `CanonicalIncidentEvidence` object with `window` and ordered `observations`. Each observation carries `observation_id`, `signal`, explicit `entity.type/id`, `field`, structured `value`, `attributes`, and `source` (`source_ref`, `source_path`, and source `locators`). Stable observation/source references are derived from modality and source locators. The projection retains every Processor-selected observation; it does not attach retrieval eligibility, importance, cause, or expected H/K metadata.

This is a minimal shared boundary, not a universal observability ontology. The Processor may deterministically aggregate source records and compute changes. The RCA Core then makes two different interpretations of the same canonical observations: a one-observation-to-one-Fact projection, and an RCA-owned search projection. Old `container_event`, `composite`, and `grouped` normalized fixture shapes are historical control artifacts, not current public inputs.

## Evidence categories

The processor research emitted typed modality evidence with coverage and uncertainty information:

- **Metric evidence:** metric identity, service/resource and labels, sample window, baseline/incident statistics, and change indicators.
- **Log evidence:** normalized pattern, example message, service/scope/severity, occurrence or rate comparison, and source records.
- **Trace evidence:** operation or service edge, latency/error observations, and contributing span context.
- **Kubernetes evidence:** pod/container/workload/event observations, including state/reason/message where present.

Selection and shaping were bounded by an evidence budget. The prototype preserved modality-specific evidence and uncertainty/coverage rather than turning absent or sparse observations into a healthy-state claim. It is not an arbitrary raw-payload passthrough.

## Ad-high-cpu example

The saved Processor capture for `ad-high-cpu-01` projects to 14 canonical observations: 2 metrics, 5 logs, and 7 traces. The Core's generic control-narration retrieval policy excludes one log from the search query, while that same observation remains available to Fact projection. No Kubernetes observation is present in this scenario's Processor output.

Examples from that fixture:

- The ad service's k8s_pod_cpu_usage observation for resource ad-544b5478f8-xfbnn records baseline_value = 0.00532728975 and incident_value = 2.4920616999200003 (recorded relative change about 466.79%). These are the fixture's values; they are not a root-cause assertion.
- A log pattern, High CPU-Load problempattern enabled, has baseline_count = 1 and incident_count = 12.
- Trace records include frontend operations and service edges. For example, the fixture records a frontend edge to ad with baseline mean about 5.175 ms and incident mean about 4.441 ms, with zero error rate in both windows.
- Kubernetes was part of the earlier telemetry research and appears in other captures, but the frozen ad-high-cpu RCA fixture has no Kubernetes observations. The earlier selected-evidence artifact likewise has an empty Kubernetes section. No Kubernetes fact should be implied for this RCA run.

The raw capture and canonical Processor output are separate artifacts: the latter reflects deterministic modality processing and source provenance, not raw payload passthrough.

The earlier estimate around 0.0039 → 2.5035 (about 637%) belongs to a different processing view and is not substituted for the saved capture's exact canonical values.

## Experimental findings: more telemetry is not automatically better

The notebook-export PNGs are supplied separately and are not required for this Markdown to render. Scores and paired counts below are transcribed from the experiment summary supplied for this documentation pass; the corresponding experiment notebooks were not present in the inspected workspaces, so these values were not independently recomputed here. They describe the tested dataset/setup only and have no statistical-significance claim.

### Experiment 1 — adding logs

![Metrics-only vs metrics plus logs: Top-1 accuracy](assets/experiments/ex1_metric-only_vs_metrics+logs_top-1-accuracy.png)

In the reported run, metrics-only accuracy was about **62.74%**, versus **41.98%** for metrics plus logs. This is evidence that adding unfiltered log evidence can distract or add noise in a particular setup—not that logs are generally harmful.

![Paired outcomes for adding log evidence](assets/experiments/ex1_effect-of-adding-log-evidence.png)

The paired outcomes were 19 improved, 63 worsened, 70 correct in both, and 60 wrong in both. This motivates evidence shaping and provenance-aware selection instead of blindly increasing model context.

### Experiment 2 — adding traces

![Metrics-only vs metrics plus traces: Top-1 accuracy](assets/experiments/ex2_metrics-only_vs_metrics+traces_top-1-accuracy.png)

The reported metrics-only result was about **73.94%**, compared with **69.72%** for metrics plus traces. In this tested setup, trace evidence was not uniformly beneficial.

![Paired outcomes for adding trace evidence](assets/experiments/ex2_effect-of-adding-trace-evidence.png)

The paired outcomes were 21 improved, 27 worsened, 78 correct in both, and 16 wrong in both. The design implication is not to discard traces; it is to preserve their source role and select context relevant to the current question.

## Guarantees and limitations

The demonstrated processing path is deterministic for a fixed captured input and configuration: it parses supported capture shapes, creates structured modality evidence, and preserves available source identity. It does not guarantee complete collection, universal source compatibility, or semantic correctness of any later RCA hypothesis.

This remains research/prototype telemetry processing, not a production observability platform. The clean RCA demo starts from normalized incident evidence; arbitrary telemetry ingestion and integrated production connectors are outside its current runtime boundary. Sparse sampling, aggregation choices, source-specific schema drift, and missing Kubernetes observations can all limit what the normalized evidence says.
