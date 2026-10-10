# Migration inventory and canonical evidence boundary

The entries below preserve provenance for the earlier frozen RCA implementation that produced `R/rca_demo_milestone/artifacts/fresh_pipeline_smoke_20261004/summary.json`. That implementation and its saved normalized/query inputs remain historical regression controls. The current public Processor-to-Core boundary is the canonical evidence contract described in the update note at the end of this document.

## Current official pipeline status

`RCAPipeline` is the one supported RCA execution pipeline. The Demo API, `scripts/run_prepared_demo.py`, release regression runner, and tests use it. It builds and verifies all Facts, retrieves H/K, sends the complete Fact set through reasoning, and rejects oversized complete requests at the provider boundary. All nine prepared fixtures that pass catalog/manifest integrity checks can run. Seven scenarios are demo-ready; `crash-loop-backoff-01` and `downstream-latency-01` remain experimental after prior live outputs failed usefulness/reference-integrity acceptance.

The complete Generator and Validator requests are guarded by the configurable prepared-demo budget (default 7,000 estimated tokens using ceil(UTF-8 bytes / 4)). The estimate is not a provider tokenizer or quota guarantee. An earlier prepared-demo iteration included one identical-request Validator retry for a structured Groq `json_validate_failed` response and optional shared pacing. Both were removed from the supported Demo v1 path; Groq's bounded transport retries remain active. The earlier recovery passed offline tests and was not exercised in successful live runs.

Accepted live status: missing-secret-01 PASS; application-failure-01 PASS with qualified hypotheses; ad-high-cpu-01 PASS with qualified hypotheses; dependency-unavailable-01 PASS with explicitly qualified Payment-side uncertainty; messaging-failure-01 PASS with qualifications preserving the measured zero consumer lag; cart-failure-01 PASS with qualified network/dependency hypotheses and successful Valkey counterevidence; memory-leak-01 PASS as a qualified short-window memory-growth investigation, not proof of a persistent leak. Crash-loop-backoff-01 produced only speculative causes despite direct exit-42 evidence; downstream-latency-01 failed Validator current-F reference integrity. These are prepared-demo outcomes, not claims of confirmed root causes or arbitrary telemetry support. See [architecture](architecture.md), [runbook](demo_runbook.md), and [verification](verification.md).

Path prefixes below are exact Windows workspace roots:

- `R` = `D:\Dev\SideProjects\rca-ai\otel_demo_dataset`
- `E` = `D:\Dev\SideProjects\rca-ai\e2e-local-demo`

The historical migration call graph is `R/rca_demo_milestone/fresh_pipeline_smoke.py:main` → `run_scenario` → `build_fact_view`, `retrieve_context`, `request_for_facts`, `provider_call`, `compact_validator_request`, `assemble_result`, and `reassemble_from_fresh`. The current `RCAPipeline` constructs every Fact from canonical input and never reduces the Fact set. The run manifest records source/code hashes and model configuration. The old `release_smoke.py` alone is **not** the source of truth for the normalized-evidence boundary: it loaded saved Fact Views and context. Its `provider_call` and frozen request-template constants were imported by the final fresh runner.

Statuses in the historical entries below describe the original port. The canonical evidence boundary migration at the end supersedes earlier input-shape/query-input descriptions.

### 1. Normalized input contract

Purpose: define the demo boundary consumed by fresh Fact construction and retrieval.

Frozen source: `R/rca_demo_milestone/fresh_pipeline_smoke.py:28-38,40-103`; scenario inputs `R/missing_secret_stage1_structure_ablation_20261001_runs/B/evidence_values.json`, `R/reasoning_core_freeze_gate_20261001_runs/6042abea-caae-4e3c-b4e9-baaa988f8f8e/reasoning_evidence_view.json`, and `R/grounding_v2_spike_20261002/artifacts/ad-high-cpu-01/evidence_builder.json`. Missing-secret and application-failure retrieval additionally consumed their saved normalized `incident_evidence.json` fixtures; ad retrieval consumed `R/retrieval_experiment/queries/ad-high-cpu-01.txt`.

Evidence that canonical: `fresh_pipeline_smoke.py:NORMALIZED` and `INCIDENT_EVIDENCE` were read inside `run_scenario`/`retrieve_context`, not the prior Fact View/context artifacts; `summary.json` reports 21, 52, and 14 fresh Facts.

Target: `src/rca_ai/domain/models.py` for the eventual input contract; fixtures under `data/demo/`.

Frozen behavior that MUST NOT change: start after normalization; preserve each fixture's existing entity, field, value, source, and ordering; do not parse raw provider telemetry.

Dependencies: scenario normalized fixtures and existing normalized retrieval-query representation.

Migration notes: **STATUS: SUPERSEDED BY CANONICAL EVIDENCE MIGRATION.** `IncidentInput` now contains `incident_id` and `CanonicalIncidentEvidence`. The old normalized mappings and separately prepared retrieval inputs are retained only as historical controls; callers do not supply either public field.

### 2. Domain models

Purpose: represent Facts, source records, hypotheses, validator outputs, and final results.

Frozen source: dict shapes created in `R/rca_demo_milestone/fresh_pipeline_smoke.py:40-103`, consumed by the historical pipeline and assembler; strict LLM object shapes in the request artifacts listed below.

Evidence that canonical: the final runner passed dictionaries directly between these functions and validated model JSON against the saved schemas; no shared typed RCA domain-model module was imported.

Target: `src/rca_ai/domain/models.py` and `domain/enums.py`.

Frozen behavior that MUST NOT change: distinct F/H/K identities, exact Fact value, separate validator decision/support dimensions, and no inferred Fact fields.

Dependencies: normalized input shapes, generator/validator schemas, assembler output.

Migration notes: **STATUS: EXTENDED FOR CANONICAL EVIDENCE.** `src/rca_ai/domain/models.py` defines `CanonicalIncidentEvidence`, `CanonicalObservation`, `EvidenceEntity`, `EvidenceSource`, and `IncidentInput(incident_id, evidence)` in addition to the frozen RCA semantic models. The canonical types retain modality/value/source structure without RCA importance or diagnosis metadata.

### 3. Fact View Builder

Purpose: project normalized records into immutable, stable-ID Facts.

Frozen source: `R/rca_demo_milestone/fresh_pipeline_smoke.py:build_fact_view`; integrity checks in `R/rca_demo_milestone/pipeline.py:verify_fact_view`, `verify_composite_fact_view`, and `verify_grouped_fact_view`. The earlier projection lineage is `R/source_faithful_hypothesis_20261002/run.py:prepare` and `R/hypothesis_generation_benchmark_20261002/run.py:prepare`.

Evidence that canonical: `run_scenario` freshly called `build_fact_view` on each `NORMALIZED` input, saved `fact_view.json`, and checked each projection; the final result matched prior Fact Views only in the post-run comparison audit.

Target: `src/rca_ai/facts/builder.py`.

Frozen behavior that MUST NOT change: deterministic F1…Fn order; exact normalized values; source path and entity ownership; no semantic paraphrase or causal edge.

Dependencies: normalized input contract; integrity verifiers.

Migration notes: **STATUS: REPLACED AT THE INPUT BOUNDARY.** `src/rca_ai/facts/builder.py` now has one generic observation-to-Fact projection and independent deterministic re-projection verification. It copies explicit entity, field, structured value, source reference, and source path; it has no backend or Kubernetes field-name ownership logic. The former container_event/composite/grouped builders and their expected Fact Views describe historical curation, not the current public contract.

### 4. Complete Fact submission and request budget

Purpose: keep source evidence complete and fail visibly when a full request exceeds the local estimate.

Current source: `src/rca_ai/pipeline/orchestrator.py` and `src/rca_ai/pipeline/request_budget.py`.

Behavior: `RCAPipeline` sends every built Fact to Generator and each Validator call. `BudgetGuardProvider` measures the complete serialized request and rejects it before transport when it exceeds the configured estimate. The guard does not change the request.

Dependencies: complete Fact View, provider contracts, and explicit request-budget errors.

### 5. History Retrieval

Purpose: retrieve analogous incidents as precedent, never current proof.

Frozen source: `R/rca_demo_milestone/fresh_pipeline_smoke.py:retrieve_context`; for missing-secret/application-failure it imported `E/app/retrieval/service.py:RetrievalService`, `E/app/corpus.py:CorpusRepository`, `E/app/source_bridge.py:build_query_text,evidence_from_payload`, and the underlying `E/app/retrieval/bm25.py`, `rrf.py`; for ad-high-cpu it called `R/retrieval_experiment/src/bm25_retriever.py:BM25Index` over the frozen query file and corpus.

Evidence that canonical: final fresh artifacts record query, ranking, IDs, and source store. The clean canonical Processor-to-Core runtime now applies the same structured channel BM25 + RRF History path to all three captures; the former ad plain-query run is retained only as historical comparison evidence.

Target: `src/rca_ai/retrieval/history.py`.

Frozen behavior that MUST NOT change: fresh retrieval from corpus, recorded order/score and source identity; History remains precedent; no saved ranking/result injection.

Dependencies: normalized query input, historical corpus, retrieval representation, BM25/channel/RRF code.

Migration notes: **STATUS: STRUCTURED-ONLY CANONICAL INPUT; ENGINE UNCHANGED.** `src/rca_ai/retrieval/projection.py` deterministically renders `CanonicalIncidentEvidence` using the existing field allowlists/renderers. `retrieve_history()` and `retrieve_knowledge()` now accept only this structured projection; input representation cannot select an algorithm. History always uses the existing per-channel BM25 + RRF path. Knowledge retains its existing BM25 ranking over `knowledge_key + claim` using the same canonical rendered query. The old string-based plain History retrieval implementation has been removed; its saved query/result remains a historical control only. `HistoryRetrievalResult` diagnostics and retrieval scoring parameters are unchanged.

### 6. Domain Knowledge Retrieval

Purpose: retrieve sourced general semantics separately from History.

Frozen source: `R/rca_demo_milestone/fresh_pipeline_smoke.py:retrieve_context`; `R/retrieval_experiment/src/bm25_retriever.py:BM25Index,K1,B` with `knowledge_key + claim`, top three, positive-score items passed forward.

Evidence that canonical: the final `retrieval_result.json` in each scenario records BM25 query, ranking, score, and selected K IDs; `run_scenario` passed only its fresh `context["domain_knowledge"]` to H generation/validation.

Target: `src/rca_ai/retrieval/knowledge.py`.

Frozen behavior that MUST NOT change: lowercase Unicode word tokenization; `k1=1.5`, `b=0.75`; unchanged key/claim indexing, top three and positive-score filter; K is interpretation, not incident evidence.

Dependencies: normalized retrieval query; sourced knowledge corpus.

Migration notes: **STATUS: UNCHANGED ENGINE, CANONICAL QUERY SOURCE.** `src/rca_ai/retrieval/knowledge.py` consumes the Core-generated query projection; BM25 (`k1=1.5`, `b=0.75`), lowercase Unicode tokenization, `knowledge_key + claim`, top-three ranking and positive-score filtering are unchanged. The external caller no longer supplies retrieval-specific material.

### 7. History store

Purpose: supply immutable historical retrieval text and resolution context.

Frozen source: `R/retrieval_experiment/corpus/historical_incidents.jsonl`, its `corpus_freeze_manifest.json`, and `E/app/corpus.py:CorpusRepository` for missing/app. The ad path read the same JSONL directly.

Evidence that canonical: `fresh_pipeline_smoke.py:CORPUS` points to this JSONL; `retrieve_context` read it fresh for every scenario; the final manifest records its SHA-256.

Target: `data/history/` plus `src/rca_ai/retrieval/history.py` store access.

Frozen behavior that MUST NOT change: retrieval uses historical evidence text; resolution fields are precedent, not current Facts.

Dependencies: corpus JSONL and freeze manifest.

Migration notes: **STATUS: MIGRATED.** Exact corpus bytes and `corpus_freeze_manifest.json` are copied to `data/history/`. The JSONL SHA-256 is `1b2052bb17eeae39a1e1dbc2dd5c7ed8d599dc15efeb59445e6de1d25c1ca167`; the loader verifies this manifest hash, retains corpus order and source IDs, and does not mutate source records. The channel path reproduces the frozen resolution-context projection only after ranking; the plain path retains the frozen retrieval-record field subset. Both remain `HistoricalContext`/H, never current Facts.

### 8. Domain Knowledge store

Purpose: supply exact claims and provenance for general system semantics.

Frozen source: `R/missing_secret_sourced_repair_20261001/knowledge.json`.

Evidence that canonical: `fresh_pipeline_smoke.py:KNOWLEDGE` was loaded during each fresh `retrieve_context`; the final manifest records SHA-256 `c1e806eda30b5d78b10896bc8a68690b2a409094a2a5b8c3f86f84bdfbd11890`.

Target: `data/knowledge/`.

Frozen behavior that MUST NOT change: unchanged knowledge key, claim, and provenance; do not add items or turn a general claim into current evidence.

Dependencies: BM25 DK retrieval.

Migration notes: **STATUS: MIGRATED.** Exact source bytes are copied to `data/knowledge/knowledge.json`, SHA-256 `c1e806eda30b5d78b10896bc8a68690b2a409094a2a5b8c3f86f84bdfbd11890`. Regression tests pin this hash and preserve store order, exact claims, knowledge keys, and source provenance. Retrieval outputs remain `KnowledgeItem`/K and never become current Facts.

### 9. Provider client and retry behavior

Purpose: send strict structured requests and distinguish provider failures from semantic output.

Frozen source: `R/rca_demo_milestone/release_smoke.py:provider_call`, imported by `fresh_pipeline_smoke.py`; equivalent earlier callers in `run_missing_secret.py` and `run_application_failure.py` were not called by the final runner.

Evidence that canonical: `run_scenario` invoked imported `provider_call` for one generation request and each candidate validation. `attempts.json` records HTTP status, retries, finish reason, latency, and token usage.

Target: `src/rca_ai/providers/groq.py`.

Frozen behavior that MUST NOT change: `httpx` POST to Groq chat completions; no streaming/tools; identical request on 429, timeout/transport error, or 5xx; at most three total attempts; honor `Retry-After` or bounded 5/15-second delay; require completed content and parse JSON. Model/configuration remains frozen.

Dependencies: `httpx`, credential, request templates, `jsonschema` validation after response.

Migration notes: **STATUS: MIGRATED.** `src/rca_ai/providers/groq.py` ports the canonical `release_smoke.py:provider_call` HTTP POST to Groq Chat Completions, generic JSON assistant-content parsing, completion check (`finish_reason == "stop"`), usage/response metadata, and per-attempt rate-limit/latency audit data. The clean provider reads `GROQ_API_KEY` from the process environment and never reads or copies the research `.secrets` file. It serializes the caller-supplied request once so each retry sends the identical body; it owns no prompts, schemas, or RCA policy. It retries only the canonical status allowlist `{429, 500, 502, 503, 504}` and timeout/transport failures, with at most three total attempts; numeric `Retry-After` is honored for 429, otherwise delays are 5 then 15 seconds. Other statuses are surfaced immediately as provider failures with safe/redacted response detail. Mocked tests use `httpx.MockTransport`; no live request is made.

### 10. Hypothesis Generator implementation

Purpose: propose candidate hypotheses from selected exact Facts and fresh H/K context.

Frozen source: `R/rca_demo_milestone/run_application_failure.py:request_for_facts`; `R/rca_demo_milestone/fresh_pipeline_smoke.py:run_scenario`; `R/rca_demo_milestone/run_missing_secret.py:validate_generation`; imported provider client above.

Evidence that canonical: final `generation/request.json` and `semantic_response.json` exist for every scenario; the runner called request construction, provider, and deterministic schema/ref validation exactly once per scenario.

Target: `src/rca_ai/reasoning/generator.py`.

Frozen behavior that MUST NOT change: current Facts are immutable input, H/K separate, zero to three candidate hypotheses accepted by deterministic validation, no forced diagnosis or semantic repair. Use the exact prompt/schema/config artifacts below.

Dependencies: complete current Facts, H/K context, provider, prompt/schema, JSON Schema validator.

Migration notes: **STATUS: MIGRATED.** `src/rca_ai/reasoning/generator.py` builds the frozen request with the complete current Fact set, H/K aliases and record representation, and deterministic schema/count/ID/reference checks. Provider failures propagate and completed-but-invalid outputs raise `GenerationValidationError`. No semantic response is used as runtime input and no live provider call is made by offline tests.

### 11. Generator prompt

Purpose: define H-generation semantics and source-role boundaries.

Frozen source: system message in `R/missing_secret_h_final_contract_20261002/artifacts/request.json`; the final runner loaded that exact template through `R/rca_demo_milestone/release_smoke.py:GEN_TEMPLATE`.

Evidence that canonical: final run prompt SHA-256 `2902e2200777ea4731cd0baaf9cff616e9ee637c0a1344202fbc9d32607c98de` across all three fresh requests; only the user-message input payload was substituted.

Target: `src/rca_ai/reasoning/prompts.py`.

Frozen behavior that MUST NOT change: prompt text verbatim, with Facts/H/K substituted as data; no scenario hints or post-run tuning.

Dependencies: generator template and input serialization.

Migration notes: **STATUS: MIGRATED.** `src/rca_ai/reasoning/prompts.py` stores the system message verbatim. The UTF-8 SHA-256 regression assertion matches the frozen hash `2902e2200777ea4731cd0baaf9cff616e9ee637c0a1344202fbc9d32607c98de`; all three reconstructed requests carry the exact same system message. No scenario-specific prompt data was added.

### 12. Generator schema

Purpose: require structured candidate IDs, explanations, Fact/H/K refs, assumptions, and unresolved items.

Frozen source: `response_format.json_schema.schema` in `R/missing_secret_h_final_contract_20261002/artifacts/request.json`; `R/rca_demo_milestone/run_missing_secret.py:validate_generation` adds deterministic ID/ref/count checks.

Evidence that canonical: final generator schema SHA-256 `26df3bd25892a50bdad1859b31d1a3fe1dd35fdf92f15fce9954d25abcc10119`; strict mode was true in every saved generation request.

Target: `src/rca_ai/reasoning/schemas.py`.

Frozen behavior that MUST NOT change: exact provider-compatible strict JSON Schema and deterministic post-parse checks; no unsupported `uniqueItems`.

Dependencies: `jsonschema`, supplied F/H/K identifiers.

Migration notes: **STATUS: MIGRATED.** `src/rca_ai/reasoning/schemas.py` stores the exact provider-compatible schema and name. Its canonical `json.dumps(schema, sort_keys=True)` SHA-256 matches `26df3bd25892a50bdad1859b31d1a3fe1dd35fdf92f15fce9954d25abcc10119`; strict mode is pinned in the request. Deterministic validation preserves the frozen maximum of three hypotheses, unique IDs, per-field unique/known F/H/K aliases, and assumption/unresolved caps without causal or semantic judgments.

### 13. Hypothesis Validator implementation

Purpose: keep, qualify, or reject a useful candidate while reporting independent support level.

Frozen source: `R/rca_demo_milestone/pipeline.py:compact_validator_request`; `R/rca_demo_milestone/run_missing_secret.py:validate_validator`; `R/rca_demo_milestone/fresh_pipeline_smoke.py:run_scenario`; imported provider client.

Evidence that canonical: final runner made one fresh validator call per generated H; `validation/<H ID>/request.json` and `semantic_response.json` were saved and checked for candidate identity and F refs.

Target: `src/rca_ai/reasoning/validator.py`.

Frozen behavior that MUST NOT change: `KEEP`/`KEEP_QUALIFIED`/`REJECT` distinct from `STRONG`/`PLAUSIBLE`/`WEAK`/`CONTRADICTED`; lack of causal proof alone is not rejection; qualifications are separate from Facts; no H rewrite.

Dependencies: candidate H, complete current Fact objects, fresh H/K, prompt/schema, provider.

Migration notes: **STATUS: MIGRATED.** `src/rca_ai/reasoning/validator.py` builds one independent request per candidate, maps outputs into `ValidationResult`, and enforces exact schema/identity/current-F-reference checks. `incident_basis.evidence` remains compact. Provider failures propagate; completed invalid output raises `ValidatorValidationError`. The wrapper adds no causal-proof threshold or semantic decision rule.

### 14. Validator prompt

Purpose: specify qualification-oriented validation rather than a proof checker.

Frozen source: system message in `R/missing_secret_h_validator_contract_20261002/artifacts/request.json`, loaded through `R/rca_demo_milestone/release_smoke.py:VAL_TEMPLATE`; payload replaced in `compact_validator_request`.

Evidence that canonical: final validator prompt SHA-256 `1b61f29d658c079b27b18ca0d0ea3e59b96e3989f21eef0368d9a1d17c86e6b6` in all saved validation requests.

Target: `src/rca_ai/reasoning/prompts.py`.

Frozen behavior that MUST NOT change: exact semantic text; no stricter policy, prompt tuning, or extra validation stage.

Dependencies: saved template and current candidate/F/H/K payload.

Migration notes: **STATUS: MIGRATED.** `src/rca_ai/reasoning/prompts.py` stores the effective final-run system message verbatim. Its UTF-8 SHA-256 matches `1b61f29d658c079b27b18ca0d0ea3e59b96e3989f21eef0368d9a1d17c86e6b6`; the Generator prompt remains unchanged.

### 15. Validator schema

Purpose: structure decision, support, incident basis, violations, qualifications, relation assessment, and unresolved items.

Frozen source: base schema in `R/missing_secret_h_validator_contract_20261002/artifacts/request.json`, with the one frozen compact transformation in `R/rca_demo_milestone/pipeline.py:compact_validator_request`.

Evidence that canonical: the effective schema in final `validation/*/request.json` has SHA-256 `3fc8c2fe12d2748fc934cfe3ae0bd50ca0db1a13891d71df7922d1e6daeebc06`; the base template schema is **not** the effective final schema. Strict output and `additionalProperties=false` remain.

Target: `src/rca_ai/reasoning/schemas.py`.

Frozen behavior that MUST NOT change: `incident_basis: {"evidence": ["F…"]}` and all other useful fields/semantics; identity and ref checks after parsing.

Dependencies: base template, compact transformation, `jsonschema`.

Migration notes: **STATUS: MIGRATED.** `src/rca_ai/reasoning/schemas.py` carries the final effective compact schema, not the base template schema. Canonical `json.dumps(schema, sort_keys=True)` SHA-256 matches `3fc8c2fe12d2748fc934cfe3ae0bd50ca0db1a13891d71df7922d1e6daeebc06`; strict mode and `additionalProperties=false` are preserved, with `incident_basis: {evidence: [...]}`. Regression tests explicitly reject the older role-per-F array.

### 16. Result Assembler

Purpose: produce API/UI-ready candidate results without another semantic transformation.

Frozen source: `R/rca_demo_milestone/assembler.py:assemble_result,resolve_sources`; call/reassembly in `R/rca_demo_milestone/fresh_pipeline_smoke.py:run_scenario,reassemble_from_fresh`.

Evidence that canonical: every final `assembly_verification.json` reports exact reassembly equality and resolvable F/H/K refs; no provider call occurred after validation.

Target: `src/rca_ai/pipeline/assembler.py`.

Frozen behavior that MUST NOT change: only validator-approved F refs enter `evidence_refs`; H/K stay separate; hypothesis and qualifications remain labeled; rejected H is not presented as retained; original records are dereferenced without paraphrase.

Dependencies: Fact/H/K stores, generated candidate, validator result.

Migration notes: **STATUS: MIGRATED.** `src/rca_ai/pipeline/assembler.py` ports `assemble_result` and `resolve_sources` over the Phase 1 domain types and lightweight retrieval result metadata. It matches validations by candidate ID, preserves Generator order, omits `REJECT`, sources `evidence_refs` only from Validator `incident_basis.evidence`, and preserves hypothesis text, H/K aliases, qualifications, and Validator unresolved items without rewriting. Typed F/H/K stores are indexed separately and unknown, duplicate, wrong-role, or overlapping source IDs fail closed. Exact `final_result.json` and `resolved_sources.json` equality passes for all three frozen scenarios; repeated assembly is identical. No provider, retrieval-algorithm, or LLM call is used.

### 17. Final RCA result schema

Purpose: define the public `incident_id` plus zero or more candidate results.

Frozen source: runtime object assembled in `R/rca_demo_milestone/fresh_pipeline_smoke.py:run_scenario,reassemble_from_fresh` and `R/rca_demo_milestone/assembler.py:assemble_result`; example concrete outputs in `R/rca_demo_milestone/artifacts/fresh_pipeline_smoke_20261004/<scenario>/final_result.json`.

Evidence that canonical: each final JSON was freshly assembled and exactly reproduced from saved fresh H/validator/F/H/K records. The shape is `{incident_id, candidate_results:[{analysis,hypothesis,evidence_refs,history_refs,knowledge_refs,qualifications,validation_unresolved}]}`.

Target: `src/rca_ai/api/schemas.py` and `src/rca_ai/domain/models.py`.

Frozen behavior that MUST NOT change: provenance separation; no duplicated synthetic Evidence text; zero candidates is a valid abstention shape.

Dependencies: assembler and original stores.

Migration notes: **STATUS: MIGRATED FOR PHASE 7.** The existing `RCAResult`, `CandidateResult`, `CandidateAnalysis`, and `CandidateHypothesis` contracts in `src/rca_ai/domain/models.py` are used directly; no duplicate hierarchy was added. Serialized results match all three frozen `final_result.json` artifacts exactly. Empty `candidate_results` remains valid; public API transport schema work remains a later phase.

### 17a. Pipeline Orchestrator

Purpose: coordinate the migrated deterministic, retrieval, Generator, Validator, and assembler stages without adding semantic behavior.

Frozen source: `R/rca_demo_milestone/fresh_pipeline_smoke.py:run_scenario`; there was no separate reusable orchestration component in the research workspace.

Evidence that canonical: `run_scenario` builds/verifies the Fact View, freshly retrieves H/K context, then selects Facts using the exact Generator request size including that context; it generates once, validates each candidate in order, and assembles deterministically.

Target: `src/rca_ai/pipeline/orchestrator.py`.

Frozen behavior that MUST NOT change: request-size callback uses the existing Generator request builder and byte estimator; provider and contract failures propagate; zero hypotheses cause zero Validator calls and assemble as an empty result; no stage repairs, ranks, or rewrites semantic content; no files are written by core orchestration.

Dependencies: all migrated domain, facts, retrieval, reasoning, provider-injected Generator/Validator, and assembler components.

Migration notes: **STATUS: MIGRATED.** `RCAPipeline.run()` preserves the final runner's operational order and exposes actual stage outputs in `PipelineRunResult`. Mock-provider integration tests reproduce the frozen `final_result.json` exactly for all three scenarios. This is a wiring proof only; no live provider calls are made.

### Historical release regression record — 20261005T072148Z

Artifact directory: `artifacts/release_regression_20261005T072148Z/`. This successful live run used the pre-migration normalized/query input contract. It is historical evidence for the frozen semantic core only; it does not verify the new canonical evidence boundary.

### 18. Demo fixtures

Purpose: provide repeatable normalized scenario inputs at the demo boundary.

Frozen source: the three `NORMALIZED` paths and two `INCIDENT_EVIDENCE` paths in `R/rca_demo_milestone/fresh_pipeline_smoke.py:28-38`; ad query `R/retrieval_experiment/queries/ad-high-cpu-01.txt`; hashes in `R/rca_demo_milestone/artifacts/fresh_pipeline_smoke_20261004/manifest.json`.

Evidence that canonical: `run_scenario` freshly loaded each normalized fixture; `retrieve_context` read its query input. Prior Fact Views, retrieval contexts, and semantic outputs were comparison-only or unused.

Target: `data/demo/` and `tests/fixtures/`.

Frozen behavior that MUST NOT change: exact fixture bytes and source hashes when copied; no raw connector input or scenario-specific fabricated fact.

Dependencies: input contract, History/DK stores, retrieval query representation.

Migration notes: **STATUS: HISTORICAL INPUTS.** The source captures now feed `process_capture_canonical`; normalized Fact Views and retrieval-input artifacts remain comparison controls and are not loaded by the release runner.

### 19. Regression and freeze tests

Purpose: guard structure, complete Fact fidelity, reference validity, provider contract, and deterministic reassembly.

Frozen source: `R/rca_demo_milestone/tests/test_contract.py`, `test_assembly.py`, `test_release_smoke.py`; final fresh-run checks in `R/rca_demo_milestone/fresh_pipeline_smoke.py:main,run_scenario,reassemble_from_fresh`; evidence in `R/rca_demo_milestone/artifacts/fresh_pipeline_smoke_20261004/{manifest.json,summary.json,<scenario>/fact_integrity.json,<scenario>/assembly_verification.json}`.

Evidence that canonical: the successful run saved fresh intermediate artifacts and exact reassembly results for all three; the focused/processor test invocation reported 37 passing tests after the run.

Target: `tests/unit/`, `tests/integration/`, `tests/fixtures/`.

Frozen behavior that MUST NOT change: source hashes, Fact IDs/values, complete Fact submission, F/H/K role checks, prompt/schema hashes, frozen provider config, and saved-output reassembly equality.

Dependencies: all migrated components and immutable fixtures.

Migration notes: **STATUS: EXTENDED.** `tests/integration/pipeline/test_processor_canonical_e2e.py` runs the three saved captures through Processor v1.1, the canonical parser, Core projections, retrieval, complete Fact reasoning, and assembly with fake semantic providers. This is deterministic wiring/provenance coverage, not live model validation.

## Original planned target structure (historical)

```text
src/rca_ai/
├── domain/
│   ├── models.py
│   └── enums.py
├── facts/
│   ├── builder.py
├── retrieval/
│   ├── history.py
│   └── knowledge.py
├── reasoning/
│   ├── generator.py
│   ├── validator.py
│   ├── prompts.py
│   └── schemas.py
├── providers/
│   └── groq.py
├── pipeline/
│   ├── orchestrator.py
│   └── assembler.py
└── api/
    ├── app.py
    ├── routes.py
    └── schemas.py
```

This was the Phase 0 proposal; most listed core modules were later implemented and reviewed in phases. The API subtree remains outside the current runtime.

## Canonical evidence boundary migration

**Current status:** implemented in the Processor v1.1 bridge and clean Core Layer 1.

**Execution distinction:** the RCA Demo v1 runner loads prepared canonical fixtures and invokes the official `RCAPipeline`; it does not invoke either Processor entry point. The Processor bridge and structural-only entry point remain separate integration/research paths. The demo live outcomes are recorded in [verification.md](verification.md).

- Processor target: `rca_processor_v1_1/canonical.py` (`to_canonical_evidence`) and `process_capture_canonical`. It converts every selected metric/log/trace/Kubernetes observation to a stable, source-linked canonical observation. Processor log output no longer carries `retrieval_eligible` or `quarantine_reason`.
- Core targets: `src/rca_ai/domain/models.py`, `src/rca_ai/facts/builder.py`, `src/rca_ai/retrieval/projection.py`, and `src/rca_ai/pipeline/orchestrator.py`.
- The Fact projection is one canonical observation to one Fact. Entity ownership is resolved in the Processor contract; no Kubernetes field-name logic remains in Core.
- Retrieval renderers and BM25/RRF engines are unchanged. Core owns the generic control-narration exclusion; an excluded log remains a Fact.
- Historical normalized Fact Views and retrieval inputs remain controls only. Their scenario-specific curation is not reconstructed as policy.
- Deterministic fake-provider integration covers all three saved captures in `tests/integration/pipeline/test_processor_canonical_e2e.py`; prepared-demo fixtures and tests are separate and live results are documented in `docs/verification.md`.

The early sections above record the lineage of frozen algorithms and schemas. Where their old input fixture counts or query-source descriptions differ from this update, the canonical boundary migration is current and the old artifacts are historical comparison data.
