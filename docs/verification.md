# RCA Demo v1 verification record

## Scope

The verified live scope is the three tracked prepared inputs only. It does not establish arbitrary telemetry ingestion, production generalization, or that an LLM hypothesis is the true root cause. The Generator proposes explanations; the Validator may retain qualified hypotheses while exposing unsupported assumptions or contradictions.

## Accepted live E2E outcomes

| Scenario | Execution | Grounding / interpretation |
|---|---|---|
| missing-secret-01 | PASS | Accepted for the prepared input; the result is evidence-linked and limited to the available Kubernetes observations. |
| application-failure-01 | PASS | Qualified hypotheses accepted. The Validator explicitly surfaced the checkout-latency contradiction and qualification; this is not an established checkout-to-payment causal diagnosis. |
| ad-high-cpu-01 | PASS | Qualified hypotheses accepted. CPU increase is observed; proposed mechanisms remain hypotheses, not confirmed causes. |

The final ad-high-cpu run made one Generator call and three Validator calls using openai/gpt-oss-120b. All 13 Facts remained intact. Each request passed the local 7,000 estimated-token guard. The successful run had no 400 or 429 response and did not trigger Validator recovery. Optional pacing honored the provider's 86.4-second reset header between semantic calls.

The ad-high-cpu execution artifacts were written under the ignored local artifacts/experiments/prepared_demo_final_ad_high_cpu_20261006T145936Z directory in the telemetry workspace. Raw provider artifacts are not part of this source-controlled verification note.

## Offline verification

The prepared-demo regression covers:

- Deterministic Fact construction and source-reference resolution.
- Complete Fact preservation through Generator and each Validator request.
- Fact Selector bypass for PreparedDemoPipeline.
- H/K retrieval and request construction.
- Complete request-budget guards, including each retry attempt.
- Exact structured json_validate_failed classification and one-retry limit.
- Optional pacing and default-pacing-disabled behavior.
- Separation from the default RCAPipeline.run().
- Prepared runner fixture loading, argument selection, pacing wiring, and summaries.

Final cleanup verification ran the full suite: **162 passed**. The focused prepared-demo, provider-wrapper, request-budget, and runner subset passed: **46 passed**.

Run the current suite with:

~~~powershell
python -m pytest -q -p no:cacheprovider
~~~

The suite is offline and uses fake providers. The final cleanup verification result is recorded below after running the command against this tree.

## Recovery and budget notes

The Validator recovery path passed offline tests for exact structured error matching, identical request replay, a maximum of two semantic attempts, and error propagation. It was **not exercised in the accepted successful live run**.

The local request estimate is ceil(UTF-8 serialized request bytes / 4); it is not the Groq tokenizer and is not a quota guarantee. Provider-reported usage, where available, is separate.

## Reproducibility boundary

The version-controlled prepared JSON files and selection manifest are under tests/fixtures/prepared_demo/. Runtime loading does not read ignored experiment directories or historical telemetry captures. The frozen History and Knowledge corpora are version-controlled under data/.
