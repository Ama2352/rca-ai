# Accepted demo limitations

- Generated hypothesis wording may occasionally overreach slightly while remaining explicitly labeled as inference.
- Pod/container wording is not always perfect.
- Validator qualifications do not catch every minor wording or scope issue.
- Retrieval may return weakly relevant historical or Domain Knowledge context; provenance still separates it from current Facts.
- Groq may rate-limit requests; the frozen retry policy is bounded and does not tune requests.
- The demo begins at normalized evidence, not arbitrary raw telemetry. Raw connectors and Source Adapters are outside its scope.

These are accepted observations from the frozen demo research. They are not permission to silently change prompts, models, schemas, retrieval thresholds, or validation policy during migration.
