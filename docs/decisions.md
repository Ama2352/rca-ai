# Frozen decisions

1. The RCA Core accepts one `CanonicalIncidentEvidence` value from the telemetry Processor. Raw telemetry collection and backend connectors remain upstream research/prototype work and are not invoked by the clean Core.
2. Current Facts are source-faithful and immutable. Deterministic construction must not summarize, infer causes, or strengthen a normalized value.
3. Input-budget reduction uses deterministic selection of whole Facts, never LLM summarization or derived Facts.
4. `F`, `H`, and `K` are separate provenance namespaces. History is precedent; Domain Knowledge is general semantics; neither proves a current incident fact.
5. The Generator proposes candidate explanations and may return multiple competing hypotheses or abstain. It does not force one diagnosis.
6. The Validator can `KEEP`, `KEEP_QUALIFIED`, or `REJECT`, while independently reporting `STRONG`, `PLAUSIBLE`, `WEAK`, or `CONTRADICTED`. An unproven causal relation is normal in a hypothesis and does not alone require rejection.
7. Assembly and final factual rendering are deterministic. No LLM rewrites a validated result or an immutable Fact.
8. Frozen H Generator/provider configuration: Groq `openai/gpt-oss-120b`, `reasoning_effort=medium`, `include_reasoning=false`, `temperature=0`, `max_completion_tokens=4096`, strict JSON Schema output. Retry identical requests only for 429, timeout, 5xx, or transport failure; three total attempts maximum.
9. The Processor owns telemetry identity, modality, deterministic transformation, entity ownership, and provenance. The RCA Core owns its distinct deterministic Fact and retrieval projections; retrieval eligibility is never a Processor-supplied observation property.

Future comments and docstrings should explain **why** these invariants exist and state each important module’s responsibility, inputs/outputs, and boundary. Avoid comments that merely narrate syntax.
