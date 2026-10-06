# RCA Demo v1 limitations

- The system proposes evidence-grounded hypotheses; it does not guarantee a correct or confirmed root-cause diagnosis.
- A hypothesis retained as KEEP_QUALIFIED may include disclosed assumptions, uncertainty, or contradictions. The qualification does not turn the claim into an observation.
- Validator qualifications do not guarantee that every wording, scope, or semantic issue will be identified.
- Pod/container wording may be imprecise.
- History or Domain Knowledge retrieval may be weakly relevant. H/K provenance is kept separate from current Facts.
- The prepared-demo budget guard uses ceil(serialized UTF-8 bytes / 4), not the provider tokenizer or a quota guarantee.
- Groq may rate-limit requests. Existing provider retries are bounded; optional pacing is not a quota guarantee.
- The prepared-demo Validator json_validate_failed recovery is offline-tested but was not exercised during the successful final live retest.
- Live verification covers only missing-secret-01, application-failure-01, and ad-high-cpu-01 using their reviewed prepared evidence. It does not establish behavior on arbitrary incident inputs.
- The prepared-demo runtime begins from prepared canonical evidence. It does not ingest arbitrary raw telemetry or invoke the telemetry Processor/connectors.

These limits do not authorize silent changes to prompts, models, schemas, retrieval, or validation policy.
