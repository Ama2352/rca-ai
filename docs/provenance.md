# Provenance boundary

| Namespace | Meaning | May represent current observed Evidence? |
|---|---|---|
| `F` | Immutable Fact from this incident’s normalized evidence | Yes |
| `H` | Historical incident and resolution context | No; precedent only |
| `K` | General sourced Domain Knowledge | No; interpretation only |
| Hypothesis | Generated explanatory inference | No |
| Qualification | Validator warning or narrower observed form | No |

Only original `F` records may populate current Evidence. History, Domain Knowledge, hypothesis wording, and validator rationale must never be promoted into immutable Facts. The result stores references to F/H/K records separately; an API/UI dereferences each reference from its original store rather than asking an LLM to summarize it.

Fact construction preserves the normalized source’s entity, field, value, source reference, and source path. Optional selection returns existing Fact objects without modification. The assembler checks reference namespaces and identities, and a saved result must be reproducible exactly from the same stored inputs and semantic outputs.
