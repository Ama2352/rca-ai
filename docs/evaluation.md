# Evaluation & Verification

RCA Demo v1 is an evidence-grounded incident investigation assistant built around prepared canonical incident evidence, historical retrieval, LLM-based hypothesis generation, independent validation, and deterministic result assembly.

Unlike the earlier RCAEval research, which measured root-cause service localization accuracy, this evaluation focuses on the **correctness of the implemented pipeline and the investigative usefulness of its outputs**.

The evaluation asks four questions:

| Evaluation Question | Objective |
|---|---|
| **EQ1 — Evidence Integrity** | Does the system preserve current incident observations and their provenance throughout execution? |
| **EQ2 — Execution Reliability** | Can the supported pipeline execute prepared incidents and produce structurally valid results? |
| **EQ3 — Investigative Usefulness** | Do retained hypotheses provide meaningful, appropriately qualified explanations of the available evidence? |
| **EQ4 — Failure Transparency** | Does the system distinguish insufficient evidence, speculative explanations, and execution failures? |

This document summarizes the prepared demo scenarios, recorded verification outcomes, known failure cases, and limitations of the current evaluation.

The reported results are based on saved verification records. They are not a fresh execution of the live provider pipeline.

---

## 1. Evaluation Scope

### 1.1. Supported Demo Boundary

RCA Demo v1 accepts reviewed, prepared canonical incident evidence.

The evaluation covers the pipeline:

```text
Prepared Canonical Evidence
           |
           v
   Fact Construction
           |
           v
 History + Knowledge Retrieval
           |
           v
   Hypothesis Generator
           |
           v
   Independent Validator
           |
           v
 Deterministic Assembler
           |
           v
        RCAResult
```

The system uses Groq `openai/gpt-oss-120b` for hypothesis generation and Cerebras `gpt-oss-120b` for independent validation in the supported demo configuration.

The Core does not ingest raw Prometheus, OpenSearch, Jaeger, or Kubernetes API responses at runtime.

Raw telemetry acquisition and preprocessing were explored separately during development and are not part of the supported demo execution path.

### 1.2. What This Evaluation Measures

The evaluation examines three distinct levels of correctness.

**Structural correctness**

Whether the supplied observations, evidence references, output schemas, and provenance boundaries are preserved.

**Execution correctness**

Whether the pipeline completes, exposes failures appropriately, and produces a valid structured result.

**Investigative usefulness**

Whether a retained hypothesis provides a meaningful explanation that is consistent with the observed incident while exposing unsupported assumptions and uncertainty.

These properties should not be conflated.

A structurally valid response can contain a weak or unhelpful hypothesis.

Likewise, an apparently plausible explanation can be unsuitable for retention if it references nonexistent current evidence.

### 1.3. What This Evaluation Does Not Establish

The verification records do not establish:

- General root-cause diagnosis accuracy on unseen production incidents.
- That every retained hypothesis identifies the true injected fault.
- That the Validator detects every unsupported causal claim.
- Production availability or scalability.
- Mean Time to Resolution improvements.
- Arbitrary raw telemetry ingestion support.

The earlier RCAEval localization results are documented separately in [Experiments](experiments.md).

---

## 2. Prepared Evaluation Scenarios

The demo includes nine prepared scenarios derived from controlled microservice and Kubernetes incidents.

Each scenario contains a reviewed subset of canonical observations rather than a complete raw telemetry capture.

The `selection_manifest.json` records selected observation identifiers, source-capture references, inclusion rationales, and known evidence gaps.

Every included observation retains its original canonical content and provenance.

### 2.1. Scenario Inventory

| Scenario | Incident Focus | Facts | Recorded Status |
|---|---|---:|---|
| `application-failure-01` | Checkout and Payment Failure | 14 | Verified |
| `ad-high-cpu-01` | Ad Service High CPU | 13 | Verified |
| `cart-failure-01` | Cart Storage Connection Failure | 5 | Verified |
| `dependency-unavailable-01` | Payment Dependency Unavailable | 8 | Verified |
| `memory-leak-01` | Email Service Memory Growth | 5 | Verified |
| `messaging-failure-01` | Order Messaging Slowdown | 9 | Verified |
| `missing-secret-01` | Telemetry Docs Startup Failure | 5 | Verified |
| `downstream-latency-01` | Shipping Slowdown | 4 | Experimental |
| `crash-loop-backoff-01` | Container Restart Loop | 3 | Experimental |

**Seven scenarios have accepted live end-to-end verification records. Two remain experimental.**

The distinction is based on the recorded execution and investigation outcomes, not merely whether a scenario's input conforms to the schema.

All nine inputs are available in the demo catalog, but experimental scenarios are not represented as accepted RCA demonstrations.

### 2.2. Evidence Coverage

The scenarios cover several diagnostic patterns.

| Failure Pattern | Representative Evidence |
|---|---|
| Application-level errors | Warning logs, failed operations, changes in successful transactions |
| CPU saturation | Resource metrics, application log changes, trace behavior |
| Dependency connectivity | Connection failure logs, RPC observations, service relationships |
| Service unavailability | RPC status changes and downstream errors |
| Resource growth | Container memory measurements and related execution context |
| Messaging anomalies | Kafka-related metrics, log patterns, and operation observations |
| Kubernetes configuration failure | Container waiting states and Kubernetes events |
| Restart behavior | Container termination details, restart metrics, and events |
| Downstream latency | Operation and service-edge latency changes |

Not every scenario contains all four telemetry modalities.

For example, the prepared `missing-secret-01` input contains only Kubernetes observations, while `application-failure-01` contains metrics, logs, traces, and Kubernetes observations.

The Core supports mixed-modality evidence without requiring identical modality coverage across incidents.


### 2.3. Dataset Limitations

The prepared inputs are intentionally bounded.

They do not establish that:

- All original telemetry was preserved.
- The selected observations represent a complete causal timeline.
- Missing modalities were unavailable in the original environment.
- Every relevant diagnostic signal was selected.

These boundaries matter when interpreting an inconclusive hypothesis.

An explanation can remain uncertain because the prepared evidence does not contain enough information to establish the underlying mechanism.

---

## 3. Verification Methodology

Evaluation uses complementary deterministic tests and live end-to-end executions.

### 3.1. Offline Verification

Offline tests use fake inference providers.

They validate the pipeline's structural and execution contracts without requiring live LLM requests.

The recorded test coverage includes:

- Canonical Fact construction.
- Fact-source preservation.
- Complete Fact forwarding.
- Historical and Domain Knowledge retrieval.
- F/H/K reference resolution.
- Generator and Validator response contracts.
- Deterministic result assembly.
- Request-budget enforcement.
- Provider error propagation.
- Prepared scenario loading and manifest validation.
- API and frontend behavior.

These checks are intended to detect implementation regressions.

They do not measure the semantic quality of live LLM explanations.

### 3.2. Live End-to-End Verification

A live scenario execution:

1. Loads the prepared canonical evidence.
2. Constructs and verifies the complete Fact View.
3. Retrieves relevant historical incidents and knowledge.
4. Invokes the Groq Hypothesis Generator.
5. Independently validates each generated candidate using Cerebras.
6. Checks response structure and reference integrity.
7. Assembles the final `RCAResult`.
8. Records the resulting hypotheses, qualifications, or execution failures.

An accepted live result must complete the relevant contracts and provide a usable investigation result within the recorded scenario's available evidence.

A completed provider request alone is insufficient.

### 3.3. Outcome Classification

The verification records distinguish several outcomes.

| Outcome | Meaning |
|---|---|
| Verified | Accepted live end-to-end outcome under the prepared-input evaluation |
| Verified, qualified | Accepted result whose causal claims retain explicit uncertainty |
| Experimental — speculative | Pipeline execution may succeed, but the investigation output is not sufficiently useful |
| Experimental — failed | Execution or validation fails before producing an accepted final result |

These are demonstration verification labels, not probabilistic confidence scores or ground-truth diagnostic accuracy measurements.

---

## 4. EQ1 — Does the System Preserve Evidence Integrity?

The first evaluation question concerns whether the system preserves the distinction between current incident observations and generated reasoning.

### 4.1. Fact Preservation

The Fact Builder deterministically maps each supplied canonical observation into a source-linked Fact.

The supported pipeline passes the complete Fact set to both the Generator and the independent Validator calls.

The intended invariants are:

- No current Fact is invented by an LLM.
- No Fact value is paraphrased into a stronger causal claim.
- No current Fact is silently removed to satisfy the request budget.
- Every current Fact retains its entity, field, value, and source identity.
- Historical and Knowledge references cannot become current Facts.

### 4.2. Provenance Reference Validation

Three namespaces are maintained:

| Reference | Source |
|---|---|
| `F` | Current incident observations |
| `H` | Retrieved historical incidents |
| `K` | Sourced Domain Knowledge |

A candidate hypothesis may refer to all three, but only current `F` references can populate current-incident evidence.

The final Assembler resolves references from their corresponding stores.

An unknown or wrong-namespace reference is not silently accepted as evidence.

### 4.3. Verified Behavior

The saved verification records report intact Fact counts and resolved references for the accepted prepared scenarios.

Examples include:

- `ad-high-cpu-01`: all 13 Facts preserved.
- `dependency-unavailable-01`: eight Facts preserved.
- `messaging-failure-01`: nine Facts preserved.
- `cart-failure-01`: five Facts preserved.
- `memory-leak-01`: five Facts preserved.

The `selection_manifest.json` provides an additional offline audit of where the included canonical observations originated.

![Current evidence panel showing source-linked Facts and technical-source controls](assets/ui/ui-evidence.png)

*The evaluation interface exposes Facts from the prepared incident evidence for inspection.*

### 4.4. Answer to EQ1

**The recorded verification supports deterministic Fact preservation and provenance integrity across the accepted prepared scenarios.**

This establishes the integrity of the evidence supplied to the Core.

It does not establish that the prepared evidence is complete or that the LLM's causal interpretation is correct.

---

## 5. EQ2 — Can the Pipeline Execute the Prepared Scenarios Reliably?

Seven prepared scenarios have accepted live end-to-end verification records.

The results are summarized below.

### 5.1. Accepted Scenarios

| Scenario | Recorded Execution | Main Verification Finding |
|---|---|---|
| Missing Secret | PASS | Evidence-linked Kubernetes startup investigation |
| Checkout and Payment Failure | PASS | Qualified hypotheses; checkout-latency contradiction surfaced |
| Ad Service High CPU | PASS | CPU increase observed; proposed causes kept as hypotheses |
| Payment Dependency Unavailable | PASS | Leading hypothesis qualified; Payment-side state not established |
| Order Messaging Slowdown | PASS | Competing qualified hypotheses; no unsupported claim of measured lag increase |
| Cart Storage Connection Failure | PASS | Connectivity hypothesis qualified against successful sampled dependency spans |
| Email Service Memory Growth | PASS, qualified | Memory growth observed; memory-leak mechanism not established |

These outcomes show that the prepared pipeline can execute incidents with different evidence compositions.

They do not imply that all retained hypotheses were definitively correct.

### 5.2. Recorded Execution Times

The verification record includes timings for several accepted scenarios.

| Scenario | Recorded Duration |
|---|---:|
| Payment Dependency Unavailable | 9.11 s |
| Order Messaging Slowdown | 11.92 s |
| Cart Storage Connection Failure | 12.84 s |
| Email Service Memory Growth | Approximately 13 s |

These timings come from individual recorded live runs.

They should not be treated as a statistically meaningful latency benchmark or a guarantee of current provider performance.

Provider quota, response behavior, and the number of Validator calls can significantly affect execution time.

### 5.3. Provider Behavior

The recorded executions also demonstrate that provider outcomes are handled separately from analysis semantics.

For example:

- `messaging-failure-01` encountered one Groq HTTP 429 and recovered using the provider's bounded transport retry policy.
- `cart-failure-01` completed its Generator and three Validator calls without recorded retries.
- `dependency-unavailable-01` completed one Generator call and three Validator calls without a recorded Groq 429.

The current Core does not add automatic semantic retries or response repair when a Validator returns an invalid result.

A provider failure or validation contract failure remains an execution failure.

### 5.4. Answer to EQ2

**The recorded live runs establish accepted end-to-end execution for seven prepared scenarios under the supported pipeline configuration.**

However, they do not establish reliability across arbitrary incident inputs, production loads, or external provider conditions.

The two experimental scenarios reveal additional limitations discussed below.

---

## 6. EQ3 — Are the Generated Hypotheses Investigatively Useful?

A structurally correct result can still contain an explanation that is too speculative or overly confident.

For this reason, the verification records considered whether the retained hypotheses were meaningfully connected to the observed evidence and whether important uncertainty remained visible.

Four examples illustrate the distinction.

### 6.1. Case Study A — Missing Secret

**Scenario:** `missing-secret-01`

The prepared evidence contains Kubernetes records describing a container startup failure.

Observed information includes:

- A container waiting state.
- `CreateContainerConfigError`.
- A Kubernetes event stating that a named Secret was not found.

The available Domain Knowledge describes Kubernetes startup behavior involving required Secrets.

These observations provide a direct basis for investigating whether the missing Secret prevents the container from starting.

The accepted outcome remains limited to what the available evidence establishes.

For example, the observed event does not independently prove that the Secret is globally absent, why its reference was configured incorrectly, or whether other startup issues also exist.

**Evaluation insight:** Strong incident-specific observations can support a useful hypothesis without eliminating every uncertainty about the underlying configuration.


### 6.2. Case Study B — Checkout and Payment Failure

**Scenario:** `application-failure-01`

The prepared evidence reports:

- Invalid-token warning messages during the incident.
- Increased Payment Charge errors.
- Increased Checkout-to-Payment errors.
- A decrease in successful transaction completion logs.

These observations support investigating an application-level Payment failure that may affect Checkout.

However, the saved verification also identified a checkout-latency contradiction that required explicit qualification.

The accepted result therefore did not establish a fully proven causal chain from the token warnings to every observed Checkout failure.

**Evaluation insight:** Retaining a useful hypothesis while identifying contradictory or incomplete evidence is preferable to presenting an unsupported definitive root cause.

![Checkout and Payment Failure investigation hypothesis with its support level](assets/ui/ui-hypothesis.png)

![Validator qualifications comparing proposed claims with observed evidence](assets/ui/ui-validation.png)

*The result retains a useful hypothesis while showing unsupported causal scope as a qualification.*

### 6.3. Case Study C — Cart Storage Connectivity

**Scenario:** `cart-failure-01`

The prepared evidence includes a Cart log reporting failure to connect to its storage dependency.

This supports investigating a Cart-to-Redis/Valkey connectivity issue.

However, the same prepared evidence also contains sampled Cart-to-Valkey trace operations that completed successfully.

The verification record therefore accepted a qualified connectivity hypothesis rather than a blanket claim that the storage service was completely unavailable.

**Evaluation insight:** Current evidence may simultaneously support a localized failure and contradict an overgeneralized explanation.

A useful RCA result must preserve both aspects.

### 6.4. Case Study D — Email Service Memory Growth

**Scenario:** `memory-leak-01`

The prepared metrics show increases in Email container memory usage.

This supports an investigation into memory growth.

However, increasing memory measurements alone do not establish a memory leak.

A confirmed leak generally requires additional evidence about persistent allocation behavior, object retention, or application memory management.

The accepted live result retained qualified candidates and explicitly marked the memory-leak claim as unproven without profiling evidence.

**Evaluation insight:** A meaningful investigation hypothesis can identify a suspected failure mechanism without presenting it as an observed fact.

### 6.5. Answer to EQ3

**The accepted verification records show examples of useful, evidence-linked hypotheses that expose uncertainty, contradictory observations, and unverified causal claims.**

This is a qualitative finding from the prepared scenarios.

It does not establish a general hypothesis-quality score or prove that the Validator correctly identifies every unsupported explanation.

---

## 7. EQ4 — Does the System Expose Unsuccessful Investigations Correctly?

Two prepared scenarios were intentionally left experimental after live evaluation.

They illustrate different reasons why an investigation may not satisfy acceptance criteria.

### 7.1. Container Restart Loop — Structurally Valid but Investigatively Weak

**Scenario:** `crash-loop-backoff-01`

The prepared evidence includes:

- A container that terminated with exit code 42.
- Recorded restart behavior.
- Kubernetes BackOff information.

A live execution completed in approximately 10.16 seconds with all three Facts intact and valid references.

The Generator and Validator produced retained, qualified hypotheses.

However, the candidate explanations speculated about causes such as Secrets, image defects, or probe misconfiguration.

They did not provide a sufficiently useful explanation of the verified injected `exit 42` failure mechanism.

The scenario was therefore **not promoted to verified status**.

This result highlights an important distinction:

**A successfully assembled, qualified hypothesis is not automatically an accepted investigation result.**

Structural integrity is necessary, but investigative usefulness is a separate criterion.

### 7.2. Shipping Slowdown — Validation Contract Failure

**Scenario:** `downstream-latency-01`

The prepared evidence includes operation and service-edge latency changes involving Shipping and related services.

A recorded live execution reached the Validator stage.

However, a Validator response referenced an identifier that was not a valid current Fact.

The reference-integrity check failed.

The pipeline did not silently remove the invalid reference, repair the response, or reinterpret the issue as insufficient incident evidence.

No accepted final `RCAResult` was assembled.

The scenario therefore remained experimental.

This demonstrates the purpose of fail-closed provenance enforcement.

A plausible response must not bypass structural evidence-reference integrity.

### 7.3. Failure Classification

The Core distinguishes three conceptually different situations.

| Situation | Interpretation | Expected Behavior |
|---|---|---|
| Generator returns no hypotheses | Valid semantic abstention | Assemble an empty candidate list |
| All hypotheses are rejected | Valid analytical outcome | Return no retained candidates |
| Provider or contract validation fails | Execution failure | Surface the failure explicitly |

These cases should not be merged into one generic “analysis failed” conclusion.

An abstention indicates that the model did not produce a candidate worth pursuing.

A contract failure indicates that the system could not safely accept the generated output.

### 7.4. Answer to EQ4

**The recorded experimental cases demonstrate that the pipeline distinguishes successful execution from investigative usefulness and rejects invalid evidence references rather than silently accepting them.**

The two experimental scenarios are retained as visible limitations.

They should not be counted as accepted RCA demonstrations.


---

## 8. Offline Regression Verification

The verification record also reports offline test-suite results collected during development.

The latest recorded pre-consolidation regression run included:

| Check | Recorded Result |
|---|---|
| Python tests | 254 passed |
| Frontend tests | 32 passed |
| TypeScript type checking | Passed |
| ESLint | Passed |
| Vite production build | Passed |
| Git diff whitespace check | Passed |

These counts are historical verification records.

They do not claim that the suite was rerun for this documentation revision or that the test counts will remain unchanged as the codebase evolves.

Offline tests use fake providers.

They verify implementation behavior without relying on the availability or output variability of live inference services.

### 8.1. Running the Offline Suite

From the project root:

```bash id="a1obcg"
python -m pytest -q -p no:cacheprovider
```

The targeted prepared-demo tests can be run separately:

```bash id="8p82p3"
python -m pytest -q -p no:cacheprovider \
  tests/integration/pipeline/test_orchestrator.py \
  tests/unit/pipeline/test_provider_observation.py \
  tests/unit/pipeline/test_request_budget.py \
  tests/unit/test_prepared_demo_runner.py
```

Frontend checks include TypeScript validation, linting, tests, and a production build.

Refer to the repository's current package scripts for the exact frontend commands.

---

## 9. Reproducing a Prepared Demo Analysis

The supported CLI runner operates on the same prepared scenario inputs as the demo application.

### 9.1. Prerequisites

- Python 3.10 or newer.
- Project dependencies installed.
- `GROQ_API_KEY` configured for live generation.
- `CEREBRAS_API_KEY` configured for live validation.
- Network access to both inference providers.

Live inference behavior may vary between runs.

Credentials should be provided through process environment variables or a supported secret store, not committed to the repository.

### 9.2. Run One Scenario

```bash id="4i6ebl"
python scripts/run_prepared_demo.py --scenario missing-secret-01
```

Another accepted scenario can be selected by its scenario identifier:

```bash id="f1vxmg"
python scripts/run_prepared_demo.py --scenario application-failure-01
```

### 9.3. Run the Scenario Suite

```bash id="es70sf"
python scripts/run_prepared_demo.py --scenario all
```

The runner processes scenarios sequentially and stops at the first execution failure.

Because two scenarios are experimental, a complete successful nine-scenario live run is not guaranteed by the current verification record.

The runner prints structured execution information, including the assembled result and provider usage when an analysis succeeds.

### 9.4. Reproducibility Boundary

The repository provides:

- Prepared canonical incident JSON files.
- A selection manifest.
- Seeded historical incident records.
- Sourced Domain Knowledge.
- The RCA Core implementation and offline tests.

The runner does not reconstruct the original raw telemetry captures or invoke upstream source adapters.

Reproducibility therefore begins at the prepared canonical evidence boundary.

Exact LLM wording and live request timing may differ because the system uses external inference services.

Deterministic stages should remain reproducible for identical inputs and saved semantic outputs.

---

## 10. Threats to Validity

### 10.1. Small Scenario Set

The live evaluation consists of nine prepared scenarios, seven of which have accepted verification records.

This is insufficient to estimate general diagnostic accuracy or failure rates with meaningful statistical confidence.

### 10.2. Curated Evidence

The evaluation uses reviewed subsets of canonical evidence.

This improves reproducibility but limits conclusions about arbitrary raw telemetry, incomplete instrumentation, and upstream evidence selection.

### 10.3. Qualitative Usefulness Judgments

The acceptance records assess investigative usefulness through individual scenario reviews.

They are not derived from a large blinded study with independent expert raters.

The verified/experimental distinction should therefore be interpreted as a documented demo acceptance decision, not a universal correctness label.

### 10.4. LLM Variability

The Generator and Validator use external language models.

Identical requests may produce different wording or candidate explanations across executions.

Contract validation reduces structural risk but cannot guarantee identical semantic outcomes.

### 10.5. Retrieval Corpus Coverage

The prepared historical corpus contains 22 seeded records, and the current Domain Knowledge collection is limited.

A useful historical precedent may be unavailable for an unseen incident.

Retrieved context can also be irrelevant or misleading.

### 10.6. Validation Is Not Causal Proof

A `KEEP` or `KEEP_QUALIFIED` decision indicates that the Validator retained a candidate under its evaluation contract.

It does not mean that the hypothesized mechanism has been independently established as the true root cause.

### 10.7. Provider and Deployment Constraints

The demo uses externally hosted inference providers and a single-host application deployment.

Provider quotas, rate limits, transient network errors, and in-memory analysis jobs limit the operational guarantees that can be drawn from the evaluation.

---

## 11. Future Evaluation Directions

Several additional evaluations would be needed to establish stronger conclusions about RCA AI.

### Groundedness Evaluation

Create an expert-reviewed dataset of candidate hypotheses and supporting observations.

Evaluate whether the Validator correctly identifies:

- Supported claims.
- Unsupported causal claims.
- Contradictions.
- Scope or entity mismatches.
- Missing qualifications.

### Diagnostic Usefulness Evaluation

Ask independent reviewers to assess whether a generated hypothesis provides a meaningful next investigation direction.

Possible criteria include plausibility, clarity, evidence coverage, and actionable uncertainty.

### Larger Incident Evaluation

Evaluate the Core on a broader set of unseen incidents with a more diverse historical corpus.

Separate retrieval relevance, hypothesis quality, and final result acceptance.

### End-to-End Operational Evaluation

Measure latency distributions, rate-limit behavior, error rates, and throughput under repeated execution.

This would also require more durable job processing and appropriate controls over provider usage.

### Production-Oriented Investigation Studies

A future study could evaluate whether the assistant helps engineers reach correct conclusions faster.

Such a study would need an independent outcome measure rather than relying only on model-generated diagnoses or Validator judgments.

These are proposed evaluations, not established capabilities of Demo v1.

---

## 12. Evaluation Summary

The prepared-demo verification records support four conclusions.

| Question | Supported Finding |
|---|---|
| **EQ1 — Evidence Integrity** | Deterministic Facts and provenance references were preserved in accepted scenario executions |
| **EQ2 — Execution Reliability** | Seven prepared scenarios have accepted live end-to-end verification records |
| **EQ3 — Investigative Usefulness** | Accepted cases demonstrate evidence-linked hypotheses with visible qualifications and unresolved assumptions |
| **EQ4 — Failure Transparency** | Experimental cases expose both speculative-but-valid results and reference-integrity failures |

The results demonstrate that RCA AI can execute an evidence-grounded hypothesis investigation workflow over its supported prepared inputs.

At the same time, the evaluation preserves important limitations.

A retained hypothesis is not automatically a confirmed root cause.

A structurally successful execution is not automatically an accepted investigation.

And accepted demonstrations on a small, curated dataset do not establish general accuracy on unseen production incidents.

**RCA Demo v1 should therefore be understood as a verified, bounded evidence-grounded investigation prototype—not an autonomous root-cause diagnosis system with established production-level accuracy.**

---

## Related Documentation

- [System Architecture](architecture.md) — Supported components and execution boundaries.
- [Core Design](core-design.md) — Deterministic evidence, retrieval, validation, and design trade-offs.
- [Experiments](experiments.md) — RCAEval research questions and findings.
- [Project README](../README.md) — Overview, setup, and live demo.
