# End-to-end architecture

The project has two related but distinct boundaries. Telemetry collection and normalization were researched and prototyped upstream; the clean, frozen RCA runtime begins at **Normalized Incident Evidence** and does not directly query telemetry systems.

~~~mermaid
flowchart TD
    A[Prometheus / OpenSearch / Jaeger / Kubernetes]
    B[Collection and source processing]
    C[Normalized Incident Evidence]
    D[RCA Core]
    E[RCAResult]
    F[API / UI]
    A --> B --> C --> D --> E --> F
~~~

- [Telemetry Contract](telemetry_contract.md) owns the researched boundary from raw telemetry to Normalized Incident Evidence.
- [RCA Contract](rca_contract.md) owns the current frozen boundary from Normalized Incident Evidence to RCAResult.

The telemetry Processor and clean RCA Core now meet at `CanonicalIncidentEvidence`. The Processor assigns objective modality/entity/provenance semantics; the Core independently projects those observations into Facts and a retrieval query. Retrieval eligibility is an RCA policy and is not emitted by the Processor.

The release runner currently calls Processor v1.1's `process_capture_canonical` entry point, which emits its existing selected modality observations. A separate `process_capture_canonical_structural` experiment preserves a broader observation set, but is not wired into the release runner and has not passed live structural-only E2E regression. That integration remains future validation work.

Earlier normalized-evidence and retrieval-query fixtures remain regression controls for the historical pipeline; their manual curation is not the current public input contract. Canonical retrieval always uses the Core's structured signal-channel projection, per-channel BM25, and RRF fusion for History; the research-stage plain-query History route is not part of the runtime. Telemetry acquisition remains a research/prototype layer, and the Core still does not claim arbitrary telemetry ingestion or production readiness.
