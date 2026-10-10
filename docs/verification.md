# RCA Demo v1 verification record

## Scope

The verified live scope is seven tracked prepared inputs only. It does not establish arbitrary telemetry ingestion, production generalization, or that an LLM hypothesis is the true root cause. The Generator proposes explanations; the Validator may retain qualified hypotheses while exposing unsupported assumptions or contradictions.

## Accepted live E2E outcomes

| Scenario | Execution | Grounding / interpretation |
|---|---|---|
| missing-secret-01 | PASS | Accepted for the prepared input; the result is evidence-linked and limited to the available Kubernetes observations. |
| application-failure-01 | PASS | Qualified hypotheses accepted. The Validator explicitly surfaced the checkout-latency contradiction and qualification; this is not an established checkout-to-payment causal diagnosis. |
| ad-high-cpu-01 | PASS | Qualified hypotheses accepted. CPU increase is observed; proposed mechanisms remain hypotheses, not confirmed causes. |
| dependency-unavailable-01 | PASS | 8 Facts; 9.11 s total. Groq Generator had no 429; three Cerebras Validator calls succeeded. The leading Checkout-to-Payment unavailability hypothesis was KEEP_QUALIFIED; Payment-side reachability/process state was explicitly unverified. |
| messaging-failure-01 | PASS | 9 Facts; 11.92 s total. Groq Generator received one HTTP 429 and recovered via existing provider transport retry; two Cerebras Validator calls succeeded. Competing hypotheses remained KEEP_QUALIFIED, including caveats that telemetry does not establish a lag increase (measured lag stayed 0). |
| cart-failure-01 | PASS | 5 Facts; 12.84 s total. Generator and all three Validators succeeded without recorded retries; all Fact/H/K references resolved. The leading Cart↔Redis connectivity explanation was qualified; successful sampled Cart→Valkey spans remain counterevidence to a blanket storage outage. |
| memory-leak-01 | PASS, qualified | 5 Facts; ~13 s command wall time. Generator returned 3.10 s provider-reported total time; Validator wall durations were not captured by the CLI summary. All three candidates were KEEP_QUALIFIED and Fact/H/K integrity held. The primary memory-leak claim was explicitly qualified as unproven without profiling evidence. |

| crash-loop-backoff-01 | NOT PROMOTED | One live execution completed in 10.16 s with 3 intact Facts and valid references, but all candidates were speculative (for example secret/configuration, image defect, or probe misconfiguration) and qualified; none explained the verified `exit 42` injection usefully. Retained as experimental. |
| downstream-latency-01 | NOT PROMOTED | One live execution failed during Validator semantic integrity: a Validator referenced a non-current Fact. No retry was made. Retained as experimental; no accepted assembled RCA result. |

The final ad-high-cpu run made one Generator call and three Validator calls using openai/gpt-oss-120b. All 13 Facts remained intact. Each request passed the local 7,000 estimated-token guard. The successful run had no 400 or 429 response and did not trigger Validator recovery. Optional pacing honored the provider's 86.4-second reset header between semantic calls.

The ad-high-cpu execution artifacts were written under the ignored local artifacts/experiments/prepared_demo_final_ad_high_cpu_20261006T145936Z directory in the telemetry workspace. Raw provider artifacts are not part of this source-controlled verification note.

## Offline verification

The following regression record predates pipeline consolidation and is retained as historical verification evidence. It is not a claim that the current workspace test suite was run.


- Deterministic Fact construction and source-reference resolution.
- Complete Fact preservation through Generator and each Validator request.
- Complete Fact preservation through the pipeline.
- H/K retrieval and request construction.
- Complete request-budget guards that reject oversized requests.
- Provider error propagation and stage timing.
- Runner fixture loading, argument handling, and summaries.

At the original three-scenario freeze, the full suite had **162 passed** and the focused prepared-demo/provider/budget/runner subset had **46 passed**. These are historical baseline counts.

## Scenario extension verification — 2026-10-08

The five-scenario result above is the historical baseline: **235 Python tests**, **30 frontend tests**, TypeScript typecheck, ESLint, and the Vite production build. The current four-scenario extension was run offline and live on 2026-10-08 with unchanged Groq Generator + Cerebras Validator routing. Cart and Memory passed Fact/H/K and schema checks; Crash is not promoted for poor investigative usefulness despite qualified decisions, and Downstream is not promoted due to a Validator current-F reference failure. No whole analysis was rerun.

Run the current suite with:

~~~powershell
python -m pytest -q -p no:cacheprovider
~~~

The suite was offline and used fake providers. The last verification before pipeline consolidation after enabling all nine scenarios recorded **254 Python tests passed**, **32 frontend tests passed**, TypeScript typecheck passed, ESLint passed, Vite production build passed, and `git diff --check` passed. No prepared fixture content was changed for the runnability update.

## Request budget

The guard measures the complete serialized Generator or Validator request using ceil(UTF-8 bytes / 4). An oversized request fails before transport, with all Facts intact. This estimate is not provider tokenization or a quota guarantee. Groq's bounded transport retry remains separate from this guard.

## Reproducibility boundary

The version-controlled prepared JSON files and selection manifest are under data/demo/. Runtime loading does not read ignored experiment directories or historical telemetry captures. The frozen History and Knowledge corpora are version-controlled under data/.
