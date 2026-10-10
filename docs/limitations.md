# RCA Demo v1 limitations

- The system proposes evidence-grounded hypotheses; it does not guarantee a correct or confirmed root-cause diagnosis.
- A hypothesis retained as KEEP_QUALIFIED may include disclosed assumptions, uncertainty, or contradictions. The qualification does not turn the claim into an observation.
- Validator qualifications do not guarantee that every wording, scope, or semantic issue will be identified.
- Pod/container wording may be imprecise.
- History or Domain Knowledge retrieval may be weakly relevant. H/K provenance is kept separate from current Facts.
- The Core request budget guard uses ceil(serialized UTF-8 bytes / 4), not the provider tokenizer or a quota guarantee.
- Groq may rate-limit requests. Its existing transport retries are bounded; `RCAPipeline` adds no pacing or Validator retry.
- Earlier prepared-demo versions tested a Validator retry for json_validate_failed, but it was removed from the supported execution path.
- The catalog exposes nine fixture- and manifest-validated inputs to analysis. Seven are verified; `crash-loop-backoff-01` and `downstream-latency-01` remain experimental because prior live outputs did not satisfy usefulness/reference-integrity acceptance. Their failures remain visible and are not retried automatically. This does not establish behavior on arbitrary incident inputs.
- The Demo API and runner begin from prepared canonical evidence. `RCAPipeline` accepts canonical evidence and does not ingest raw telemetry or invoke the telemetry Processor/connectors.

These limits do not authorize silent changes to prompts, models, schemas, retrieval, or validation policy.
