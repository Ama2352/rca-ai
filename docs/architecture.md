# Frozen demo architecture

The demo begins with **Normalized Incident Evidence** supplied as an input fixture/store. Raw collection, connectors, and Source Adapters are outside the demo boundary.

| Stage | Execution | Contract |
|---|---|---|
| Fact View | Deterministic | Project normalized entity, field, value, source ID, and source path into immutable `F` records. No paraphrase or causal inference. |
| Fact Selector | Deterministic, optional | Select whole existing Facts only when the provider input budget requires it. |
| History retrieval | Deterministic | Retrieve `H` precedent from the historical store; preserve ranking and source identity. |
| Domain Knowledge retrieval | Deterministic | Retrieve `K` general semantics from the sourced knowledge corpus; preserve ranking and provenance. |
| Hypothesis Generator | LLM | Propose zero or more competing explanations. Speculative relations remain hypotheses, with assumptions and unresolved questions. |
| Hypothesis Validator | LLM | Decide `KEEP`, `KEEP_QUALIFIED`, or `REJECT`; separately report `STRONG`, `PLAUSIBLE`, `WEAK`, or `CONTRADICTED`. Lack of direct causal proof alone is not rejection. |
| Result Assembler | Deterministic | Preserve F/H/K references and validator qualifications. Never rewrite a hypothesis or create a Fact. |
| API/UI result | Deterministic rendering | Dereference original F/H/K records in separate sections. |

The Generator and Validator are the only semantic LLM stages. No LLM call occurs after validation. Provider requests use Groq `openai/gpt-oss-120b`, medium reasoning, `include_reasoning=false`, temperature `0`, a `4096` completion-token cap, and strict structured output. Transient retries send the identical request, with at most three attempts.

Phase 0 defines this boundary and the migration map only. No stage implementation is present in `src/rca_ai/` yet. The [migration inventory](migration_inventory.md) identifies the files and exact request artifacts used by the final successful fresh-pipeline smoke, including unresolved consolidation questions.
