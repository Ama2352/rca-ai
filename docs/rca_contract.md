# RCA contract

This is the authoritative contract for the current frozen RCA core: **Normalized Incident Evidence → RCAResult**. Raw telemetry acquisition and source adapters are upstream research/prototype work described in the [Telemetry Contract](telemetry_contract.md); they are not called by this clean runtime.

## Input and execution boundary

The core receives the domain model `IncidentInput`:

- `incident_id` identifies the incident.
- `evidence` is `CanonicalIncidentEvidence`, projected by the telemetry Processor from already-processed source records. It contains a window and ordered canonical observations; it is not a raw telemetry schema.

The core does not accept arbitrary Prometheus, OpenSearch, Jaeger, or Kubernetes API payloads as its public input contract. Callers no longer provide a second RCA-specific `retrieval_input` representation.

~~~mermaid
flowchart TD
    A[Normalized Incident Evidence]
    B[Canonical Fact projection]
    C[Canonical retrieval projection and fresh H/K]
    D[Whole-Fact selection if needed]
    E[Hypothesis Generator]
    F[Validator per candidate]
    G[Deterministic Assembler]
    H[RCAResult]
    A --> B --> C --> D --> E --> F --> G --> H
~~~

Operationally, the Core independently projects canonical observations into Facts and retrieval material. Retrieval runs before selection because the selector estimates the size of the exact Generator request, including current History and Knowledge context. If the request is within budget all Facts are kept; otherwise the existing deterministic selector chooses whole Facts. It never truncates or rewrites a Fact. Historical frozen request fixtures contained manual/query-specific preparation and are not required as current runtime input.

The current release runner obtains evidence through `process_capture_canonical`, which retains the Processor's existing modality-level selection. A separate structural-only Processor experiment is not wired into the runner and has not had live E2E validation. This distinction matters when interpreting counts: the captures below describe the current canonical entry point, not the broader structural-only experiment.

| Capture | Canonical observations | Facts | Selected Facts | Retrieved H | Retrieved K |
|---|---:|---:|---:|---:|---:|
| missing-secret-01 | 19 | 19 | 9 | 3 | 3 |
| application-failure-01 | 53 | 53 | 13 | 3 | 1 |
| ad-high-cpu-01 | 14 | 14 | 14 | 3 | 2 |

These are saved-capture deterministic counts under the canonical boundary. Historical Fact Views (21/52/14) and selected counts (21/25/14) remain controls from a different, curated input pipeline, not expected equality targets. Scenario IDs name test captures; they are not production projection rules.

The Selector remains a resource guard with a frozen category-priority policy; it is not lossless evidence compression. In the separate structural-only deterministic experiment, application-failure produced 1,145 Facts and the current Selector retained 7, all metrics, because error-label text such as `ERROR` receives the highest category. That experiment made no LLM call and did not establish that the selected Facts adequately cover the incident. This is a known context-coverage limitation; the Selector policy has not been changed or validated as a modality-coverage policy.

The count differences have identifiable causes. The old missing-secret Fact View expanded Kubernetes records into 21 field-level Facts and did not use its 17 Processor metrics as current Facts; the canonical path emits 17 metric observations plus two structured Kubernetes observations. The old application-failure input omitted one Processor log pattern (`Payment request failed. Invalid token...`); the canonical path retains all seven logs. For ad-high-cpu, the control-narration log remains a Fact but is omitted from retrieval. These are historical-curation differences, not changes to retrieval ranking or semantic stages.

## Fact contract

A Fact is a deterministic, source-faithful projection with these fields:

| Field | Meaning |
|---|---|
| fact_id | Stable current-Fact identifier (F1, F2, …). |
| entity | Exact owner, represented by entity type and id. |
| field | Observed field name. |
| value | Exact source-projected value; may be a scalar or JSON-shaped value. |
| source_ref | Source record identity. |
| source_path | Locator to the projected source field. |

Facts are observations, not explanations. The builder maps each canonical observation one-to-one into a Fact, including its already explicit entity owner and source path. It must not infer root cause, paraphrase values, invent observations, or broaden scope; Kubernetes ownership is resolved upstream by the telemetry Processor.

The wire shape is intentionally small:

```json
{
  "window": {"start": 0, "end": 60},
  "observations": [{
    "observation_id": "stable-processor-id",
    "signal": "kubernetes",
    "entity": {"type": "container", "id": "telemetry-docs"},
    "field": "kubernetes.state",
    "value": {"waiting_reason": "CreateContainerConfigError"},
    "attributes": {},
    "source": {"source_ref": "source-record-id", "source_path": "/kubernetes/0", "locators": ["pods.json:items[0]"]}
  }]
}
```

Values may retain modality-specific structure. Entity ownership is already explicit at this boundary; the RCA Fact builder does not interpret Kubernetes field names or any raw backend path.

## Provenance namespaces

| Namespace | Meaning | May infer? | Current Evidence? |
|---|---|---:|---:|
| F | Current incident Fact | No | Yes |
| H | Historical precedent | No | No |
| K | General Domain Knowledge | No | No |
| Hypothesis | Proposed explanation | Yes | No |
| Qualification | Validator commentary | Yes | No |

**F = what we observed now. H = what happened before. K = what we generally know. A Hypothesis = what may explain F.** Only immutable F records may become current incident Evidence.

~~~mermaid
flowchart LR
    F[F: current Facts] --> G[Generator]
    H[H: History] --> G
    K[K: Domain Knowledge] --> G
    G --> V[Validator]
    F --> V
    V --> R[RCAResult]
    F -. evidence_refs only .-> R
~~~

History retrieval returns precedent and Knowledge retrieval returns sourced general semantics. Both remain separately addressable. The Core retrieval projection produces the structured query payload from canonical observations; every canonical incident uses signal-specific History BM25 channels followed by the existing RRF fusion. The former plain-query BM25 route was a research-stage artifact and is not a canonical runtime input. Knowledge uses the same deterministically rendered query material with BM25 over knowledge_key + claim and the frozen top-three positive-score behavior. A weakly relevant H/K result remains H/K; it is never current incident proof.

The retrieval projection uses the existing fixed modality renderers, deterministic ordering, and current log control-narration rule. That rule excludes explicit feature-flag/experiment/injection/problem-pattern state narration from search; it does not delete or relabel the observation, which remains available to Fact projection. The Processor reports the log and its source only. The Core owns the decision about whether it participates in H/K search.

## Generator contract

The frozen Groq Generator receives selected exact Facts and fresh H/K context. It returns zero to three candidate hypotheses. Each candidate keeps separate explains_fact_refs, supporting_fact_refs, history_refs, and knowledge_refs, plus assumptions and unresolved text.

The Generator may propose uncertain explanatory relations and may return multiple competing candidates. It does not create current observations, promote H/K to Facts, choose a final diagnosis, rank candidates, validate its own claims, or repair its output. A hypothesis is explicitly inference; uncertainty is expected.

## Validator contract

Each generated candidate is validated independently in one structured Validator call. Two dimensions are preserved separately:

- **Decision:** KEEP, KEEP_QUALIFIED, or REJECT.
- **Support:** STRONG, PLAUSIBLE, WEAK, or CONTRADICTED.

The Validator asks, “Is this hypothesis worth retaining, and what needs qualification?” It is not a proof checker. Lack of causal proof alone is not grounds for rejection. It may identify source, scope, entity, or factual problems as hard violations or non-fatal qualifications, under the frozen contract.

incident_basis.evidence contains current F references only. Qualifications and Validator rationale remain commentary, never Facts.

## Deterministic assembly

The assembler is deterministic and makes no LLM call. It matches validation to hypotheses by ID, omits REJECT, preserves Generator order, takes evidence_refs only from Validator incident_basis.evidence, and keeps H/K references separate. Hypothesis text, assumptions, unresolved items, qualifications, and validation unresolved items are preserved without paraphrase.

There is no final LLM rewrite: such a rewrite could silently alter text after its source references and qualifications were checked. The assembler resolves F/H/K references only in their own stores and fails closed on unknown or wrong-namespace references.

## RCAResult output

The current serialized shape includes incident_id at the result level and on each retained candidate:

~~~json
{
  "incident_id": "missing-secret-01",
  "candidate_results": [
    {
      "incident_id": "missing-secret-01",
      "analysis": {
        "decision": "KEEP_QUALIFIED",
        "support_level": "STRONG"
      },
      "hypothesis": {
        "id": "H1",
        "explanation": "The container cannot start because the referenced secret \"eda-capture-secret-does-not-exist\" is missing, causing a CreateContainerConfigError and putting the container in a waiting state.",
        "assumptions": [
          "The pod spec includes a reference to the secret \"eda-capture-secret-does-not-exist\".",
          "The secret is required (non‑optional) for container startup.",
          "The secret does not exist in the namespace at the time of pod creation."
        ],
        "unresolved": [
          "Inspect the pod specification to confirm the secret reference.",
          "Query the namespace for the existence of the secret with that name.",
          "Determine whether the secret name is a typo or was intended to be different."
        ]
      },
      "evidence_refs": ["F6", "F8", "F9", "F2", "F3", "F16"],
      "history_refs": ["H1", "H3"],
      "knowledge_refs": ["K2", "K3"],
      "qualifications": [
        {
          "claim": "The container cannot start because the referenced secret \"eda-capture-secret-does-not-exist\" is missing, causing a CreateContainerConfigError and putting the container in a waiting state.",
          "issue": "Overstates causality; missing secret is indicated but not proven as the sole cause of the container not starting.",
          "fact_refs": ["F6", "F8", "F9"],
          "observed_form": "Container is in waiting state with waiting_message indicating secret not found and waiting_reason CreateContainerConfigError."
        }
      ],
      "validation_unresolved": [
        "Inspect the pod specification to confirm the secret reference.",
        "Query the namespace for the existence of the secret with that name.",
        "Determine whether the secret name is a typo or was intended to be different."
      ]
    }
  ]
}
~~~

analysis preserves the decision/support pair. hypothesis exposes the unrewritten inference and its uncertainty. evidence_refs resolve only to current Facts; H/K references resolve from their own stores. qualifications and validation_unresolved remain Validator commentary and are separate from the hypothesis's own unresolved questions. A result with candidate_results: [] is valid.

RCAResult is the deterministic API/UI-ready data contract, not an API implementation. HTTP routes and UI rendering are downstream consumers and are outside the current clean core.

## Missing-secret walkthrough

The live release artifact is artifacts/release_regression_20261005T072148Z/missing-secret-01/:

1. **Normalized evidence → Facts:** F6 says container telemetry-docs has state = waiting; F8 preserves the source message secret "eda-capture-secret-does-not-exist" not found; F9 records waiting_reason = CreateContainerConfigError. These are separate observations with their own source_ref/source_path. F2 separately says the owning Pod phase is Pending.
2. **Retrieved context:** History aliases H1, H2, H3 resolve to historical sources H021, H018, H020; Knowledge aliases K1–K3 resolve to sourced general claims. These inform context, not current evidence.
3. **Generated proposal:** H1 explains that the named Secret may be involved in the container's startup failure. The exact explanation is preserved in the example above; the Generator's assumptions and unresolved questions stay attached to that candidate.
4. **Validation:** the saved H1 Validator response returns KEEP_QUALIFIED with STRONG support, while qualifying the causal wording. This keeps decision and support independent.
5. **Assembly:** evidence_refs are the Validator-approved current F IDs; history_refs and knowledge_refs remain aliases. The explanation is still a Hypothesis, not an Evidence item.

This illustrates the boundary: F8 records “not found by the source operation”; it does not itself establish global absence, origin, or the full cause.

## Failure, abstention, and edge cases

~~~mermaid
stateDiagram-v2
    [*] --> Generation
    Generation --> Abstention: 0 hypotheses
    Generation --> Validation: 1..3 hypotheses
    Generation --> Failure: provider or contract error
    Validation --> Disposition: KEEP / KEEP_QUALIFIED / REJECT
    Validation --> Failure: provider or contract error
    Abstention --> RCAResult: empty candidate list
    Disposition --> Assembly
    Assembly --> RCAResult
~~~

| Case | Classification | Behavior |
|---|---|---|
| Generator returns zero hypotheses | Valid semantic abstention | No Validator calls; assemble an empty result. |
| Every candidate is REJECT | Valid semantic result | No candidate is retained; observed F data remains separate. |
| Transient timeout/5xx/transport error or HTTP 429 later succeeds | Operational retry | Provider retries the identical request within the bounded policy; it is not model semantics. |
| Provider retry budget exhausted | Execution failure | Propagate provider failure; do not convert it to abstention or REJECT. |
| Malformed JSON, strict-schema violation, or unknown F/H/K reference | Contract/execution failure | Fail closed; do not silently drop or repair the invalid result. |
| Request size requires selection | Deterministic context reduction | Select whole exact Facts under the frozen policy; no Fact is shortened. |
| Live wording differs between runs | Expected LLM variability | Contract/provenance are checked; exact wording need not match. |
| Retrieved H/K not referenced by a candidate | Valid unused context | It remains in its own store and is not promoted into Evidence. |
| Reassembly from identical saved stage outputs | Deterministic check | Must reproduce the same RCAResult exactly. |

## Why BM25 + LLM?

The final architecture reflects separate research findings and design choices rather than a claim that one retrieval method wins every case.

### More modalities were not reliably better

The reported experiment summaries show lower aggregate accuracy after adding logs or traces in those particular comparisons:

![Metrics-only, BM25, and metrics plus retrieval: Top-1 accuracy](assets/experiments/ex3_metrics-only_vs_metrics+retrieval-llm_top-1-accuracy.png)

The retrieval comparison reported 60.23% for metrics-only LLM, 64.83% for BM25 Top-1, and 70.11% for metrics plus retrieved context. In that run, adding retrieval context was more useful than simply increasing telemetry context. It does not establish universal improvement.

![Paired outcomes for adding retrieval](assets/experiments/ex3_effect-of-adding-retrieval.png)

Paired outcomes for adding retrieval were 86 improved, 43 worsened, 219 correct in both, and 87 wrong in both. The reported difference versus metrics-only was about **+9.89 percentage points**.

![Effect of adding logs, traces, and retrieval](assets/experiments/ex3_effect-of-additional-evidence.png)

The supplied summary reports approximately −20.75 points for logs, −4.23 for traces, and +9.89 for retrieval. This comparison motivates relevant context selection; it does not prove that any modality is inherently good or bad.

> **Research finding:** blindly increasing the amount of evidence did not reliably improve the tested LLM results.
>
> **Design consequence:** keep source provenance, shape evidence deterministically, and retrieve/select context rather than treating all available content as equally useful.
>
> **Current frozen behavior:** whole-Fact budget selection plus deterministic BM25-family retrieval; semantic inference is isolated to Generator/Validator stages.

### BM25 and semantic reranking

BM25 supplied a deterministic, interpretable retrieval baseline. A separate experiment tested a MiniLM reranker after BM25:

![Metrics-only LLM vs BM25 plus LLM vs BM25 plus MiniLM plus LLM](assets/experiments/ex3_metrics-only+llm_vs_bm25+llm_vs_bm25+miniLM+llm_top-1-accuracy.png)

The reported Top-1 values were 0.602 for metrics-only LLM, 0.701 for BM25 + LLM, and 0.752 for BM25 + MiniLM + LLM.

![Paired outcomes: BM25 plus LLM vs BM25 plus MiniLM plus LLM](assets/experiments/ex3_paired-comparison_bm25+llm_vs_bm25+miniLM+llm.png)

For BM25 + MiniLM compared with BM25 alone, the paired counts were 46 improved, 24 worsened, 281 correct in both, and 84 wrong in both. The reranker helped on balance in this experiment but did not help every example.

**Research finding:** semantic reranking was tested and improved this reported evaluation.
**Current frozen behavior:** the clean runtime does not use MiniLM. Domain Knowledge uses the frozen BM25 ranking over the structured projection's rendered query; History uses per-signal BM25 channels and the frozen RRF fusion. The research result and shipped frozen mechanism are intentionally described separately.

Earlier diagnosis/grounding experiments also motivated explicit source roles and qualification rather than treating a proposed cause as a proven state. The final architecture therefore separates immutable F observations, H/K context, generated hypotheses, Validator qualifications, and deterministic assembly. It removed final LLM rewriting so claims cannot be silently changed after provenance checks.

> **Research finding:** semantic context interference and diagnosis-oriented grounding checks exposed a risk of rejecting or distorting a useful candidate merely because its explanatory relation was not directly observed.
>
> **Design consequence:** keep observed-state checks strict, but allow a speculative relation to remain a hypothesis and represent non-fatal scope/entity uncertainty as qualification.
>
> **Current frozen behavior:** the Validator can keep, qualify, or reject independently of support level; it is not a causal proof gate.

### Holdout observation

![Final holdout Top-1 evaluation](assets/experiments/ex4_final-holdout-evaluation_top-1-accuracy.png)

The supplied plot summary reports 75.17% on development and 75.84% on holdout. In that evaluation, the holdout score did not show an obvious development-only collapse. This is not a statistical-equivalence, production-generalization, or no-overfitting claim.

The experiment score summaries and paired counts in this section were supplied for documentation; source notebooks/exports containing the underlying calculations were not available in the inspected workspace. Treat them as dataset/setup-specific reported results until those artifacts are added alongside the requested PNGs.

## Guarantees and limitations

The frozen implementation and regression tests support:

- deterministic Fact projection and integrity verification;
- deterministic whole-Fact selection;
- separate F/H/K namespaces and fail-closed reference resolution;
- strict structured Generator and Validator contracts;
- decision and support as independent dimensions;
- deterministic assembly and exact reassembly;
- no final LLM rewrite; and
- execution/provider failure remaining distinct from semantic abstention.

These are contract and pipeline guarantees, not a guarantee that a hypothesis is semantically correct. Live wording may vary; hypotheses may remain speculative or qualified; retrieval may return weakly relevant context; Groq may rate-limit requests. The core starts from normalized evidence and is not production-ready or an arbitrary raw-telemetry ingestion system. Experimental accuracy values apply only to the tested dataset/configuration.
