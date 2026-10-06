# RCA Investigation frontend draft

Frontend-only React + TypeScript + Vite demo. It reads saved JSON fixtures and
does not call the Python RCA pipeline.

## Run locally

```powershell
cd frontend
npm install
npm run dev
```

## Mock data

`src/mock/` contains the frozen `RCAResult` and paired `resolved_sources`
fixtures copied from `tests/fixtures/pipeline/assembler/`. The small scenario
adapter keeps those public shapes intact and pairs resolved source entries to
retained candidates by their emitted array order.

The one- and two-candidate choices are labeled preview states derived by
selecting the first one or two saved Missing Secret candidates in Generator
order. The abstention preview uses the valid public result shape with an empty
`candidate_results` array, a clearly marked preview incident ID, and no
invented reason.

Display components consume the public result and resolved source types in
`src/contract.ts`. Current Facts, historical context, and domain knowledge
remain separate in both the data and the page.
