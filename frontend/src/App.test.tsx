import { afterEach, expect, test, vi } from "vitest"
import "@testing-library/jest-dom/vitest"
import { cleanup, render, screen, waitFor, within } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import App from "./App"
import type { AnalysisJob, Fact } from "./contract"
import { scenarioOverviews } from "./scenarioOverviews"

afterEach(() => { cleanup(); vi.unstubAllGlobals() })

const incidents = [
  { id: "missing-secret-01", source: "custom-k8s", readiness: "demo-ready", prepared_input: "data/demo/missing-secret-01.json",
    available_evidence_sources: ["kubernetes"], incident_snapshot: [{ observation_id: "observation-one", source_ref: "source-one", presentation: {
      id: "F1", signal_type: "kubernetes", title: "Telemetry Docs · Pending", statistic_kind: null,
      baseline: null, incident: null, unit: null, change: null, source_service: null,
      destination_service: null, operation: null, severity: null, state: "Pending", preview: null,
      technical: { source_ref: "source-one" }, raw: {
        fact_id: "F1", entity: { type: "container", id: "telemetry-docs" },
        field: "kubernetes.structural.state", value: { deployment: "telemetry-docs", phase: "Pending", container_state: "waiting", ready: false },
        source_ref: "source-one", source_path: "observations[0]",
      },
    } }] },
  { id: "application-failure-01", source: "otel-demo", readiness: "demo-ready", prepared_input: "data/demo/application-failure-01.json",
    available_evidence_sources: ["metric", "log", "trace", "kubernetes"] },
  { id: "ad-high-cpu-01", source: "otel-demo", readiness: "demo-ready", prepared_input: "data/demo/ad-high-cpu-01.json",
    available_evidence_sources: ["metric", "log", "trace", "kubernetes"] },
  { id: "dependency-unavailable-01", source: "otel-demo", readiness: "demo-ready", prepared_input: "data/demo/dependency-unavailable-01.json",
    available_evidence_sources: ["metric", "log", "trace", "kubernetes"] },
  { id: "messaging-failure-01", source: "otel-demo", readiness: "demo-ready", prepared_input: "data/demo/messaging-failure-01.json",
    available_evidence_sources: ["metric", "log", "trace", "kubernetes"] },
  { id: "cart-failure-01", source: "otel-demo", readiness: "demo-ready", prepared_input: "data/demo/cart-failure-01.json",
    available_evidence_sources: ["log", "trace", "kubernetes"], incident_snapshot: [] },
  { id: "downstream-latency-01", source: "otel-demo", readiness: "experimental", prepared_input: "data/demo/downstream-latency-01.json",
    available_evidence_sources: ["trace", "kubernetes"], incident_snapshot: [] },
  { id: "memory-leak-01", source: "otel-demo", readiness: "demo-ready", prepared_input: "data/demo/memory-leak-01.json",
    available_evidence_sources: ["metric", "trace", "kubernetes"], incident_snapshot: [] },
  { id: "crash-loop-backoff-01", source: "custom-k8s", readiness: "experimental", prepared_input: "data/demo/crash-loop-backoff-01.json",
    available_evidence_sources: ["kubernetes", "metric"], incident_snapshot: [] },
]
const completed = {
  analysis_id: "job-1", incident_id: "missing-secret-01", status: "completed", fact_integrity: true,
  stage: "completed", stage_label: "Completed", elapsed_seconds: 2.4,
  completed_stages: [{ stage: "preparation", seconds: 0.1 }, { stage: "evidence", seconds: 0.2 },
    { stage: "retrieval", seconds: 0.3 }, { stage: "generation", seconds: 0.6 },
    { stage: "validation", seconds: 0.7 }, { stage: "assembly", seconds: 0.1 }],
  execution_audit: { total_seconds: 2.4,
    routing: {
      generator: { provider: "Groq", model: "openai/gpt-oss-120b" },
      validator: { provider: "Cerebras", model: "gpt-oss-120b" },
    },
    rows: [
    { name: "preparation", seconds: 0.1, relationship: "exclusive" },
    { name: "evidence", seconds: 0.2, relationship: "exclusive" },
    { name: "retrieval", seconds: 0.3, relationship: "exclusive" },
    { name: "generation_provider", seconds: 0.6, relationship: "exclusive" },
    { name: "validation_provider", seconds: 0.7, relationship: "exclusive" },
    { name: "assembly", seconds: 0.1, relationship: "exclusive" },
  ] },
  facts: [{ fact_id: "F1", entity: { type: "container", id: "telemetry-docs" }, field: "phase",
    value: "Pending", source_ref: "source-one", source_path: "pods[0].phase" }],
  presented_facts: [{ id: "F1", signal_type: "kubernetes", title: "Telemetry Docs · Pending",
    statistic_kind: null, baseline: null, incident: null, unit: null, change: null,
    source_service: null, destination_service: null, operation: null, severity: null,
    state: "Pending", preview: null, technical: { source_ref: "source-one" },
    raw: { fact_id: "F1", entity: { type: "container", id: "telemetry-docs" }, field: "phase",
      value: "Pending", source_ref: "source-one", source_path: "pods[0].phase" },
  }],
  history_ids: ["H001"], knowledge_ids: ["K001"],
  validations: [],
  result: { incident_id: "missing-secret-01", candidate_results: [{
    incident_id: "missing-secret-01", analysis: { decision: "KEEP_QUALIFIED", support_level: "PLAUSIBLE" },
    hypothesis: { id: "HYP1", explanation: "A cautious working explanation.", assumptions: ["Cause unverified"], unresolved: ["  confirm   mechanism  "] },
    evidence_refs: ["F1"], history_refs: ["H001"], knowledge_refs: ["K001"],
    qualifications: [{ claim: "a cause", issue: "causation not established", fact_refs: ["F1"], observed_form: "pod pending" }],
    validation_unresolved: ["Confirm mechanism"],
  }] },
  resolved_sources_by_candidate: { HYP1: {
    evidence: [{ fact_id: "F1", entity: { type: "container", id: "telemetry-docs" }, field: "phase",
      value: "Pending", source_ref: "source-one", source_path: "pods[0].phase" }],
    history: [{ alias: "H001", source_id: "historical-1", source_type: "HISTORY",
      record: { incident_id: "past-incident", incident_summary: "Past incident context" } }],
    domain_knowledge: [{ alias: "K001", source_id: "knowledge-1", source_type: "DOMAIN_KNOWLEDGE",
      record: { knowledge_key: "known-behavior", claim: "A domain context statement" } }],
  } },
}

function apiFetch(
  status: "completed" | "failed" = "completed",
  decision: "KEEP" | "KEEP_QUALIFIED" | "REJECT" = "KEEP_QUALIFIED",
  missingPresentation = false,
  incidentRows: typeof incidents = incidents,
) {
  const calls: string[] = []
  const fetcher = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input)
    calls.push(`${init?.method ?? "GET"} ${url}`)
    if (url === "/api/demo/incidents") return Response.json({ incidents: incidentRows })
    if (url === "/api/demo/analyses") return Response.json({ analysis_id: "job-1", incident_id: "missing-secret-01", status: "queued" }, { status: 202 })
    if (url === "/api/demo/analyses/job-1") {
      if (status === "failed") return Response.json({
        analysis_id: "job-1", incident_id: "missing-secret-01", status: "failed", error: { code: "PROVIDER_FAILED" },
      })
      const result = structuredClone(completed)
      result.result.candidate_results[0].analysis.decision = decision
      if (missingPresentation) result.presented_facts = []
      return Response.json(result)
    }
    throw new Error(`Unexpected request: ${url}`)
  })
  vi.stubGlobal("fetch", fetcher)
  return calls
}

test("overview appears before analysis and does not reveal mock RCA results", async () => {
  const calls = apiFetch()
  render(<App />)
  expect(await screen.findByRole("heading", { name: "Scenario overview" })).toBeInTheDocument()
  expect(screen.getByRole("heading", { name: "Known scenario cause" })).toBeInTheDocument()
  expect(screen.getByRole("heading", { name: "Observed symptoms" })).toBeInTheDocument()
  expect(screen.getByRole("heading", { name: "Evidence snapshot" })).toBeInTheDocument()
  const snapshotHeading = screen.getByRole("heading", { name: "Evidence snapshot" })
  const snapshotSection = snapshotHeading.closest("section")!
  expect(snapshotSection).toHaveTextContent("Container state")
  expect(within(snapshotSection).getByText("Kubernetes", { exact: true })).toBeInTheDocument()
  expect(screen.getByRole("heading", { name: "Scenario Library" })).toBeInTheDocument()
  expect(screen.getByRole("heading", { name: "OpenTelemetry Demo" })).toBeInTheDocument()
  expect(screen.getByRole("heading", { name: "Custom Kubernetes" })).toBeInTheDocument()
  expect(screen.getAllByRole("button", { name: /Demo-ready/ })).toHaveLength(7)
  expect(screen.getAllByRole("button", { name: /Experimental/ })).toHaveLength(2)
  expect(screen.queryByText(/Telemetry is observation, not a confirmed root cause/i)).not.toBeInTheDocument()
  expect(screen.queryByText("A cautious working explanation.")).not.toBeInTheDocument()
  expect(calls).toEqual(["GET /api/demo/incidents"])
})

test("overview uses the refined section labels and hides source identifiers in summary rows", async () => {
  apiFetch()
  render(<App />)
  expect(await screen.findByRole("heading", { name: "Scenario overview" })).toBeInTheDocument()
  expect(screen.getByRole("heading", { name: "Analysis context" })).toBeInTheDocument()
  expect(screen.getByRole("heading", { name: "What RCA will investigate" })).toBeInTheDocument()
  expect(screen.getByText("Known cause for this prepared scenario — not generated by RCA.")).toBeInTheDocument()
  expect(screen.getByText("RCA examines the available evidence, retrieves relevant context, and evaluates possible root causes. Conclusions may remain uncertain when the evidence is incomplete.")).toBeInTheDocument()
  const overview = screen.getByRole("heading", { name: "Scenario overview" }).closest("section")!
  expect(within(overview).getByText("Demo-ready")).toHaveAttribute("title", "This scenario has been prepared for the intended demo workflow. RCA conclusions are not guaranteed.")
  expect(screen.getByRole("button", { name: "View prepared JSON" })).toBeInTheDocument()
  const evidence = screen.getByRole("heading", { name: "Evidence snapshot" }).closest("section")!
  expect(within(evidence).getByText("Container state")).toBeInTheDocument()
  expect(evidence).not.toHaveTextContent("source-one")
})

test("static scenario overviews cover all nine prepared scenarios with concise editorial content", () => {
  expect(Object.keys(scenarioOverviews).sort()).toEqual(incidents.map(({ id }) => id).sort())
  for (const overview of Object.values(scenarioOverviews)) {
    expect(overview.title.trim()).not.toBe("")
    expect(overview.description.trim()).not.toBe("")
    expect(overview.cause.trim()).not.toBe("")
    expect(overview.observations.length).toBeGreaterThanOrEqual(2)
    expect(overview.observations.length).toBeLessThanOrEqual(5)
    expect(overview.investigation.trim()).not.toBe("")
  }
})

test("curated cause and observed symptoms stay separate from RCA results before analysis", async () => {
  apiFetch()
  render(<App />)
  expect(await screen.findByRole("heading", { name: "Known scenario cause" })).toBeInTheDocument()
  expect(screen.getByRole("heading", { name: "Observed symptoms" })).toBeInTheDocument()
  expect(screen.getByText("The `telemetry-docs` deployment references a Kubernetes Secret named `eda-capture-secret-does-not-exist`, but that Secret is missing from the cluster. Kubernetes therefore cannot complete the affected container's startup configuration.")).toBeInTheDocument()
  expect(screen.getByText("The new Telemetry Docs Pod remains Pending, and its container is not ready.")).toBeInTheDocument()
  expect(screen.queryByText(/Telemetry-Docs · Pending · Pending/)).not.toBeInTheDocument()
  expect(screen.getByText(/RCA examines the available evidence/i)).toBeInTheDocument()
  expect(screen.queryByText("A cautious working explanation.")).not.toBeInTheDocument()
})

test.each([
  ["Payment Dependency Unavailable", "invalid service endpoint", "Checkout reports `UNAVAILABLE` status information for calls to Payment's `Charge` operation."],
  ["Order Messaging Slowdown", "additional processing delays", "The recorded Kafka consumer lag remains at zero, so the selected metrics do not demonstrate a growing backlog of unconsumed records."],
  ["Cart Storage Connection Failure", "connection failures while communicating", "Other observed calls to the Valkey backend do not report operation errors."],
  ["Email Service Memory Growth", "increased memory demand", "The Email container remains running and ready, and the selected traces report no operation errors."],
])("new scenario overview explains %s in plain language", async (title, cause, symptom) => {
  const calls = apiFetch()
  const user = userEvent.setup()
  render(<App />)
  await screen.findByRole("heading", { name: "Scenario overview" })
  await user.click(screen.getByRole("button", { name: new RegExp(`${title}.*Demo-ready`) }))
  expect(screen.getByText(new RegExp(cause))).toBeInTheDocument()
  expect(screen.getByText(symptom)).toBeInTheDocument()
  expect(screen.getByText("Available telemetry")).toBeInTheDocument()
  expect(screen.getByRole("button", { name: "Analyze incident" })).toBeEnabled()
  expect(calls).toEqual(["GET /api/demo/incidents"])
})

test("semantic Fact rendering shows meaning before collapsed raw JSON", async () => {
  apiFetch()
  const user = userEvent.setup()
  render(<App />)
  await screen.findByRole("heading", { name: "Scenario overview" })
  await user.click(screen.getByRole("button", { name: "Analyze incident" }))
  expect(await screen.findByRole("heading", { name: "Telemetry Docs · Pending" })).toBeInTheDocument()
  expect(screen.queryByText("null → null")).not.toBeInTheDocument()
  expect(screen.getByText("View technical source")).toBeInTheDocument()
  expect(screen.queryByText("View raw JSON")).not.toBeInTheDocument()
})

test.each([
  ["missing-secret-01", /deployment references a Kubernetes Secret named/i, /new Telemetry Docs Pod remains Pending/i, ["Kubernetes"]],
  ["application-failure-01", /payment token validation fails/i, /Payment warning logs report invalid payment tokens/i, ["Metrics", "Logs", "Traces", "Kubernetes"]],
  ["ad-high-cpu-01", /CPU-intensive processing in the Ad service/i, /reported CPU usage rises sharply/i, ["Metrics", "Logs", "Traces", "Kubernetes"]],
])("scenario overview separates the known cause from observed symptoms for %s", async (id, cause, symptom, telemetry) => {
  apiFetch()
  const user = userEvent.setup()
  render(<App />)
  await screen.findByRole("heading", { name: "Scenario overview" })
  if (id !== "missing-secret-01") {
    const title = id === "application-failure-01" ? /Checkout and Payment Failure/ : /Ad Service High CPU/
    await user.click(screen.getByRole("button", { name: new RegExp(String(title.source) + ".*Demo-ready") }))
  }
  const causeHeading = screen.getByRole("heading", { name: "Known scenario cause" })
  const causeSection = causeHeading.closest("section")!
  expect(within(causeSection).getByText(cause)).toBeInTheDocument()
  expect(screen.getByRole("heading", { name: "Observed symptoms" })).toBeInTheDocument()
  expect(screen.getByText(symptom)).toBeInTheDocument()
  expect(causeSection.compareDocumentPosition(screen.getByRole("button", { name: "Analyze incident" })) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
  expect(screen.getByText("Available telemetry")).toBeInTheDocument()
  const contextSection = screen.getByRole("heading", { name: "Analysis context" }).closest<HTMLElement>(".overview-config")!
  for (const badge of telemetry) expect(within(contextSection).getByText(badge, { exact: true })).toBeInTheDocument()
})

test("experimental scenario keeps its status while showing its static known cause", async () => {
  apiFetch()
  const user = userEvent.setup()
  render(<App />)
  await screen.findByRole("heading", { name: "Scenario overview" })
  await user.click(screen.getByRole("button", { name: /Container Restart Loop.*Experimental/ }))
  expect(screen.getByRole("heading", { name: "Known scenario cause" })).toBeInTheDocument()
  expect(screen.getByText("The container is configured to execute a command that exits with status code `42`. Because the main process terminates, Kubernetes repeatedly attempts to restart the container and applies restart backoff.")).toBeInTheDocument()
  expect(screen.getByText(/Experimental scenario: analysis is available/)).toBeInTheDocument()
  expect(screen.getByRole("button", { name: "Analyze incident" })).toBeEnabled()
})

test("explanation references stay inside their card in a dedicated row and assessments stack", async () => {
  apiFetch()
  const user = userEvent.setup()
  render(<App />)
  await screen.findByRole("heading", { name: "Scenario overview" })
  await user.click(screen.getByRole("button", { name: "Analyze incident" }))
  const card = await screen.findByRole("region", { name: /A cautious working explanation/ })
  expect(within(card).getByRole("group", { name: "Supporting sources" })).toBeInTheDocument()
  expect(within(card).getByText("Support").compareDocumentPosition(within(card).getByText("Validation")) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
})

test("raw JSON disclosure exposes the complete canonical Fact without alteration", async () => {
  apiFetch()
  const user = userEvent.setup()
  render(<App />)
  await screen.findByRole("heading", { name: "Scenario overview" })
  await user.click(screen.getByRole("button", { name: "Analyze incident" }))
  await screen.findByText("A cautious working explanation.")
  await user.click(screen.getByRole("button", { name: "View technical source" }))
  await user.click(screen.getByRole("button", { name: "View raw JSON" }))
  expect(screen.getByText(/"source_path": "pods\[0\]\.phase"/)).toBeInTheDocument()
  expect(screen.getByText(/"value": "Pending"/)).toBeInTheDocument()
  expect(screen.getByText(/"fact_id": "F1"/)).toBeInTheDocument()
})

test("histogram rate uses its semantic label and unit while dimensionless values omit a suffix", async () => {
  const histogram: Fact = {
    fact_id: "F2", entity: { type: "pod", id: "checkout-1" },
    field: "metric.structural.series", source_ref: "metric-source", source_path: "/metric/460",
    value: {
      service: "checkout", metric: "rpc_server_call_duration_seconds_count",
      metric_kind: "histogram_count", unit: "reported_unit/second",
      baseline_value: 0, incident_value: 0.047619, start: null, end: null,
      duration_ms: null, trace_id: null, span_id: null,
    },
  }
  const dimensionless: Fact = {
    fact_id: "F3", entity: { type: "pod", id: "checkout-1" },
    field: "metric.structural.series", source_ref: "dimensionless-source", source_path: "/metric/461",
    value: { service: "checkout", metric: "utilization_ratio", metric_kind: "gauge", unit: "1", baseline_value: 0.2, incident_value: 0.4 },
  }
  const job = structuredClone(completed) as AnalysisJob
  job.facts = [histogram, dimensionless]
  job.presented_facts = [
    { id: "F2", signal_type: "metric", title: "Checkout · RPC server requests", statistic_kind: "histogram_observation_rate",
      baseline: 0, incident: 0.047619, unit: "observations/s", change: "increased", source_service: "checkout",
      destination_service: null, operation: null, severity: null, state: null, preview: null,
      technical: { metric: "rpc_server_call_duration_seconds_count" }, raw: histogram },
    { id: "F3", signal_type: "metric", title: "Checkout · Utilization ratio", statistic_kind: "value",
      baseline: 0.2, incident: 0.4, unit: "1", change: null, source_service: "checkout",
      destination_service: null, operation: null, severity: null, state: null, preview: null,
      technical: { metric: "utilization_ratio" }, raw: dimensionless },
  ]
  job.resolved_sources_by_candidate!.HYP1.evidence = [histogram, dimensionless]
  job.result!.candidate_results[0].evidence_refs = ["F2", "F3"]
  vi.stubGlobal("fetch", vi.fn((input: RequestInfo | URL) => {
    const url = String(input)
    if (url === "/api/demo/incidents") return Promise.resolve(Response.json({ incidents }))
    if (url === "/api/demo/analyses") return Promise.resolve(Response.json({ analysis_id: "job-1", incident_id: "missing-secret-01", status: "queued" }, { status: 202 }))
    if (url === "/api/demo/analyses/job-1") return Promise.resolve(Response.json(job))
    throw new Error(`Unexpected request: ${url}`)
  }))

  const user = userEvent.setup()
  render(<App />)
  await screen.findByRole("heading", { name: "Scenario overview" })
  await user.click(screen.getByRole("button", { name: "Analyze incident" }))

  const histogramCard = document.getElementById("source-HYP1-F-F2")!
  expect(within(histogramCard).getByRole("heading", { name: "Checkout · RPC server requests" })).toBeInTheDocument()
  expect(within(histogramCard).getByText("Histogram observation rate · baseline → incident")).toBeInTheDocument()
  expect(within(histogramCard).getByText("0.0476 observations/s")).toBeInTheDocument()

  const dimensionlessCard = document.getElementById("source-HYP1-F-F3")!
  expect(within(dimensionlessCard).getByText("0.2", { exact: true })).toBeInTheDocument()
  expect(within(dimensionlessCard).getByText("0.4", { exact: true })).toBeInTheDocument()
  expect(within(dimensionlessCard).queryByText("0.2 1")).not.toBeInTheDocument()

  await user.click(within(histogramCard).getByRole("button", { name: "View technical source" }))
  await user.click(within(histogramCard).getByRole("button", { name: "View raw JSON" }))
  expect(within(histogramCard).getByText(/"duration_ms": null/)).toBeInTheDocument()
  expect(within(histogramCard).getByText(/"trace_id": null/)).toBeInTheDocument()
  expect(within(histogramCard).getByText(/"metric": "rpc_server_call_duration_seconds_count"/)).toBeInTheDocument()
})

test("execution durations use milliseconds, seconds, and minutes without rounding nonzero to zero", async () => {
  const { formatDuration } = await import("./App")
  expect(formatDuration(0.004)).toBe("4 ms")
  expect(formatDuration(0.041)).toBe("41 ms")
  expect(formatDuration(2.44)).toBe("2.4s")
  expect(formatDuration(59.8)).toBe("1m 0s")
  expect(formatDuration(125.2)).toBe("2m 5s")
})

test("analysis progress labels completed, current, pending, and failed stages truthfully", async () => {
  let polls = 0
  vi.stubGlobal("fetch", vi.fn((input: RequestInfo | URL) => {
    const url = String(input)
    if (url === "/api/demo/incidents") return Promise.resolve(Response.json({ incidents }))
    if (url === "/api/demo/analyses") return Promise.resolve(Response.json({ analysis_id: "job-1", incident_id: "missing-secret-01", status: "queued" }, { status: 202 }))
    if (url === "/api/demo/analyses/job-1" && ++polls > 1) return Promise.resolve(Response.json({
      analysis_id: "job-1", incident_id: "missing-secret-01", status: "failed", stage: "validation",
      stage_label: "Validating hypotheses", error: { code: "VALIDATION_FAILED", message: "Validator referenced a non-current fact" },
      completed_stages: [{ stage: "preparation" }, { stage: "evidence" }, { stage: "retrieval" }, { stage: "generation" }],
    }))
    return Promise.resolve(Response.json({ analysis_id: "job-1", incident_id: "missing-secret-01", status: "running", stage: "validation", stage_label: "Validating hypotheses", completed_stages: [{ stage: "preparation" }, { stage: "evidence" }, { stage: "retrieval" }, { stage: "generation" }] }))
  }))
  const user = userEvent.setup()
  render(<App />)
  await screen.findByRole("heading", { name: "Scenario overview" })
  await user.click(screen.getByRole("button", { name: "Analyze incident" }))
  expect(await screen.findByRole("status", { name: "Analysis progress" })).toHaveTextContent("Completed")
  expect(screen.getByText("Running")).toBeInTheDocument()
  expect(screen.getByText("Pending")).toBeInTheDocument()
  expect(await screen.findByRole("alert", {}, { timeout: 3500 })).toHaveTextContent("Validator referenced a non-current fact")
  expect(screen.getByText("Failed", { selector: ".stage-failed .stage-state" })).toBeInTheDocument()
}, 10000)

test("rate-limited analysis explains retry timing and allows one manual retry after delay", async () => {
  let posts = 0
  vi.stubGlobal("fetch", vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input)
    if (url === "/api/demo/incidents") return Promise.resolve(Response.json({ incidents }))
    if (url === "/api/demo/analyses" && init?.method === "POST") {
      posts += 1
      return Promise.resolve(Response.json({ analysis_id: `job-${posts}`, incident_id: "missing-secret-01", status: "queued" }, { status: 202 }))
    }
    if (url.startsWith("/api/demo/analyses/job-")) return Promise.resolve(Response.json({
      analysis_id: url.split("/").pop(), incident_id: "missing-secret-01", status: "failed",
      error: { code: "RATE_LIMITED", retry_after_seconds: 1 },
    }))
    throw new Error(`Unexpected request: ${url}`)
  }))
  const user = userEvent.setup()
  render(<App />)
  await screen.findByRole("heading", { name: "Scenario overview" })
  await user.click(screen.getByRole("button", { name: "Analyze incident" }))
  const retry = await screen.findByRole("button", { name: /Retry (analysis|in)/ }, { timeout: 3500 })
  expect(screen.getByRole("alert")).toHaveTextContent(/rate-limit/i)
  expect(retry).toBeDisabled()
  await waitFor(() => expect(retry).toBeEnabled(), { timeout: 2500 })
  await user.click(retry)
  expect(posts).toBe(2)
})

test("missing presentation never silently hides a cited canonical Fact", async () => {
  apiFetch("completed", "KEEP_QUALIFIED", true)
  const user = userEvent.setup()
  render(<App />)
  await screen.findByRole("heading", { name: "Scenario overview" })
  await user.click(screen.getByRole("button", { name: "Analyze incident" }))
  expect(await screen.findByRole("heading", { name: "Presentation unavailable" })).toBeInTheDocument()
  expect(screen.getAllByText("F1").length).toBeGreaterThan(0)
  expect(screen.getByText("View technical source")).toBeInTheDocument()
})

test("candidate Fact, history, knowledge, and qualification references navigate to real targets", async () => {
  apiFetch()
  const user = userEvent.setup()
  Element.prototype.scrollIntoView = vi.fn()
  render(<App />)
  await screen.findByRole("heading", { name: "Scenario overview" })
  await user.click(screen.getByRole("button", { name: "Analyze incident" }))
  await screen.findByText("A cautious working explanation.")
  for (const id of ["F1", "H001", "K001"]) {
    await user.click(screen.getAllByRole("button", { name: id })[0])
    expect(vi.mocked(Element.prototype.scrollIntoView)).toHaveBeenCalled()
  }
  expect(screen.getAllByRole("button", { name: "F1" }).length).toBeGreaterThan(1)
  expect(screen.getByRole("heading", { name: "Open questions" })).toBeInTheDocument()
  expect(screen.getByText("Generator + Validator")).toBeInTheDocument()
  expect(screen.getAllByText(/Confirm mechanism/i)).toHaveLength(1)
})

test("semantically identical historical cards group while retaining each navigable H alias and raw variant", async () => {
  const payload = structuredClone(completed) as unknown as AnalysisJob
  payload.history_ids = ["H001", "H003", "H004"]
  payload.resolved_sources_by_candidate!.HYP1.history = [
    { alias: "H001", source_id: "hist-1", source_type: "HISTORY", record: {
      incident_id: "H001", affected_component: "ad", root_cause: "Ad service CPU saturation",
      resolution_note: "Seeded resolved historical variant for retrieval testing.",
      recommended_action: "Inspect ad worker CPU and scale if demand persists.", retrieval_text: "metric variant one",
    } },
    { alias: "H003", source_id: "hist-3", source_type: "HISTORY", record: {
      incident_id: "H003", affected_component: "ad", root_cause: "Ad service CPU saturation",
      resolution_note: "Seeded resolved historical variant for retrieval testing.",
      recommended_action: "Inspect ad worker CPU and scale if demand persists.", retrieval_text: "trace variant three",
    } },
    { alias: "H004", source_id: "hist-4", source_type: "HISTORY", record: {
      incident_id: "H004", affected_component: "payment", root_cause: "Payment application rejection",
      recommended_action: "Inspect payment request validation.", retrieval_text: "different root-cause class",
    } },
  ]
  payload.result!.candidate_results[0].history_refs = ["H001", "H003", "H004"]
  vi.stubGlobal("fetch", vi.fn((input: RequestInfo | URL) => {
    const url = String(input)
    if (url === "/api/demo/incidents") return Promise.resolve(Response.json({ incidents }))
    if (url === "/api/demo/analyses") return Promise.resolve(Response.json({ analysis_id: "job-1", incident_id: "missing-secret-01", status: "queued" }, { status: 202 }))
    if (url === "/api/demo/analyses/job-1") return Promise.resolve(Response.json(payload))
    throw new Error(`Unexpected request: ${url}`)
  }))
  const user = userEvent.setup()
  Element.prototype.scrollIntoView = vi.fn()
  render(<App />)
  await screen.findByRole("heading", { name: "Scenario overview" })
  await user.click(screen.getByRole("button", { name: "Analyze incident" }))
  expect(await screen.findAllByText("Ad service CPU saturation")).toHaveLength(1)
  expect(document.querySelectorAll("article.historical-case")).toHaveLength(2)
  for (const id of ["H001", "H003", "H004"]) {
    const chips = screen.getAllByRole("button", { name: id })
    await user.click(chips[chips.length - 1])
    expect(vi.mocked(Element.prototype.scrollIntoView)).toHaveBeenCalled()
  }
  await user.click(screen.getByRole("button", { name: "View H001 source details" }))
  expect(await screen.findByText(/metric variant one|trace variant three/)).toBeInTheDocument()
})

test("open questions keep source attribution separate from readable question text", async () => {
  apiFetch()
  const user = userEvent.setup()
  render(<App />)
  await screen.findByRole("heading", { name: "Scenario overview" })
  await user.click(screen.getByRole("button", { name: "Analyze incident" }))
  const question = await screen.findByText("confirm mechanism")
  expect(question).toHaveClass("open-question-text")
  expect(screen.getByText("Generator + Validator")).toHaveClass("open-question-sources")
})

test("completed analysis displays authoritative measured execution total", async () => {
  apiFetch()
  const user = userEvent.setup()
  render(<App />)
  await screen.findByRole("heading", { name: "Scenario overview" })
  await user.click(screen.getByRole("button", { name: "Analyze incident" }))
  expect(await screen.findByRole("heading", { name: "Analysis execution" })).toBeInTheDocument()
  expect(screen.getByText("2.4s")).toBeInTheDocument()
  expect(screen.getByText("Generation provider operation")).toBeInTheDocument()
})

test("running analysis displays actual current stage without a percentage", async () => {
  let polls = 0
  vi.stubGlobal("fetch", vi.fn((input: RequestInfo | URL) => {
    const url = String(input)
    if (url === "/api/demo/incidents") return Promise.resolve(Response.json({ incidents }))
    if (url === "/api/demo/analyses") return Promise.resolve(Response.json({ analysis_id: "job-1", incident_id: "missing-secret-01", status: "queued" }, { status: 202 }))
    if (url === "/api/demo/analyses/job-1" && ++polls > 1) return Promise.resolve(Response.json(completed))
    if (url === "/api/demo/analyses/job-1") return Promise.resolve(Response.json({
      analysis_id: "job-1", incident_id: "missing-secret-01", status: "running",
      stage: "validation", stage_label: "Validating hypotheses", candidate_id: "HYP1",
      completed_stages: [{ stage: "preparation", seconds: 0.1 }, { stage: "evidence", seconds: 0.2 },
        { stage: "retrieval", seconds: 0.3 }, { stage: "generation", seconds: 0.6 }],
      elapsed_seconds: 10,
    }))
    throw new Error(`Unexpected request: ${url}`)
  }))
  const user = userEvent.setup()
  render(<App />)
  await screen.findByRole("heading", { name: "Scenario overview" })
  await user.click(screen.getByRole("button", { name: "Analyze incident" }))
  expect(await screen.findByText("Validating hypotheses", { selector: "strong" })).toBeInTheDocument()
  expect(screen.getByText("HYP1")).toBeInTheDocument()
  expect(screen.getByText(/Retrieving historical and domain context/)).toBeInTheDocument()
  expect(screen.queryByText(/% complete/i)).not.toBeInTheDocument()
})

test("catalog loading failure shows an error instead of mock incident content", async () => {
  vi.stubGlobal("fetch", vi.fn(async () => { throw new Error("backend unavailable") }))
  render(<App />)
  expect(await screen.findByRole("alert")).toHaveTextContent("backend unavailable")
  expect(screen.queryByRole("heading", { name: "Scenario overview" })).not.toBeInTheDocument()
  expect(screen.queryByRole("button", { name: "Analyze incident" })).not.toBeInTheDocument()
})

test("analyze uses the selected incident and renders real qualified result", async () => {
  const calls = apiFetch()
  const user = userEvent.setup()
  render(<App />)
  await screen.findByRole("heading", { name: "Scenario overview" })
  await user.click(screen.getByRole("button", { name: "Analyze incident" }))
  expect(await screen.findByText("A cautious working explanation.")).toBeInTheDocument()
  expect(screen.getByText(/Generator · Groq \/ openai\/gpt-oss-120b/)).toBeInTheDocument()
  expect(screen.getByText(/Validator · Cerebras \/ gpt-oss-120b/)).toBeInTheDocument()
  expect(screen.getByText("causation not established")).toBeInTheDocument()
  expect(screen.getByText("Cause unverified")).toBeInTheDocument()
  await user.click(screen.getByText("View technical source"))
  expect(screen.getByText("source-one")).toBeInTheDocument()
  expect(vi.mocked(fetch)).toHaveBeenCalledWith("/api/demo/analyses", expect.objectContaining({
    method: "POST", body: JSON.stringify({ incident_id: "missing-secret-01" }),
  }))
  expect(calls).toContain("POST /api/demo/analyses")
  expect(calls).toContain("GET /api/demo/analyses/job-1")
  expect(screen.queryByText("F22")).not.toBeInTheDocument()
})

test("Validator qualifications remain visible when the candidate decision is KEEP", async () => {
  apiFetch("completed", "KEEP")
  const user = userEvent.setup()
  render(<App />)
  await screen.findByRole("heading", { name: "Scenario overview" })
  await user.click(screen.getByRole("button", { name: "Analyze incident" }))
  expect(await screen.findByText("A cautious working explanation.")).toBeInTheDocument()
  expect(screen.getByText("Kept", { exact: true })).toBeInTheDocument()
  expect(screen.getByRole("heading", { name: "Validator qualification" })).toBeInTheDocument()
  expect(screen.getByText("causation not established")).toBeInTheDocument()
  expect(screen.getByText("pod pending")).toBeInTheDocument()
})

test("backend failure is displayed separately from an RCA abstention", async () => {
  apiFetch("failed")
  const user = userEvent.setup()
  render(<App />)
  await screen.findByRole("heading", { name: "Scenario overview" })
  await user.click(screen.getByRole("button", { name: "Analyze incident" }))
  expect(await screen.findByRole("alert")).toHaveTextContent("PROVIDER_FAILED")
  expect(screen.queryByText("No explanatory candidate was retained.")).not.toBeInTheDocument()
})

test("a completed empty RCA result is shown as abstention, not a backend failure", async () => {
  vi.stubGlobal("fetch", vi.fn((input: RequestInfo | URL) => {
    const url = String(input)
    if (url === "/api/demo/incidents") return Promise.resolve(Response.json({ incidents }))
    if (url === "/api/demo/analyses") return Promise.resolve(Response.json({ analysis_id: "job-1", incident_id: "missing-secret-01", status: "queued" }, { status: 202 }))
    if (url === "/api/demo/analyses/job-1") return Promise.resolve(Response.json({
      ...completed, result: { incident_id: "missing-secret-01", candidate_results: [] },
      resolved_sources_by_candidate: {},
    }))
    throw new Error(`Unexpected request: ${url}`)
  }))
  const user = userEvent.setup()
  render(<App />)
  await screen.findByRole("heading", { name: "Scenario overview" })
  await user.click(screen.getByRole("button", { name: "Analyze incident" }))
  expect(await screen.findByText("No explanatory candidate was retained.")).toBeInTheDocument()
  expect(screen.queryByRole("alert")).not.toBeInTheDocument()
})

test("switching incidents updates overview and clears the prior analysis", async () => {
  apiFetch()
  const user = userEvent.setup()
  render(<App />)
  await screen.findByRole("heading", { name: "Scenario overview" })
  await user.click(screen.getByRole("button", { name: "Analyze incident" }))
  await screen.findByText("A cautious working explanation.")
  await user.click(screen.getByRole("button", { name: /Ad Service High CPU.*Demo-ready/ }))
  expect(await screen.findByRole("heading", { name: "Ad Service High CPU" })).toBeInTheDocument()
  await waitFor(() => expect(screen.queryByText("A cautious working explanation.")).not.toBeInTheDocument())
})

test("an old job response cannot appear under a newly selected incident", async () => {
  let finishOldJob: (response: Response) => void = () => { throw new Error("not started") }
  vi.stubGlobal("fetch", vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input)
    if (url === "/api/demo/incidents") return Promise.resolve(Response.json({ incidents }))
    if (url === "/api/demo/analyses" && init?.method === "POST") {
      return Promise.resolve(Response.json({ analysis_id: "job-1", incident_id: "missing-secret-01", status: "queued" }, { status: 202 }))
    }
    if (url === "/api/demo/analyses/job-1") {
      return new Promise<Response>((resolve) => { finishOldJob = resolve })
    }
    throw new Error(`Unexpected request: ${url}`)
  }))
  const user = userEvent.setup()
  render(<App />)
  await screen.findByRole("heading", { name: "Scenario overview" })
  await user.click(screen.getByRole("button", { name: "Analyze incident" }))
  expect(await screen.findByRole("status")).toHaveTextContent("Analysis")
  await user.click(screen.getByRole("button", { name: /Ad Service High CPU.*Demo-ready/ }))
  finishOldJob(Response.json(completed))
  expect(await screen.findByRole("heading", { name: "Ad Service High CPU" })).toBeInTheDocument()
  await waitFor(() => expect(screen.queryByText("A cautious working explanation.")).not.toBeInTheDocument())
})

test("analysis submission stays disabled while a job is starting", async () => {
  let finishSubmission: (response: Response) => void = () => { throw new Error("not started") }
  let posts = 0
  vi.stubGlobal("fetch", vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input)
    if (url === "/api/demo/incidents") return Promise.resolve(Response.json({ incidents }))
    if (url === "/api/demo/analyses" && init?.method === "POST") {
      posts += 1
      return new Promise<Response>((resolve) => { finishSubmission = resolve })
    }
    if (url === "/api/demo/analyses/job-1") {
      return Promise.resolve(Response.json({ analysis_id: "job-1", incident_id: "missing-secret-01", status: "failed", error: { code: "PROVIDER_FAILED" } }))
    }
    throw new Error(`Unexpected request: ${url}`)
  }))
  const user = userEvent.setup()
  render(<App />)
  await screen.findByRole("heading", { name: "Scenario overview" })
  await user.click(screen.getByRole("button", { name: "Analyze incident" }))
  expect(screen.getByRole("button", { name: "Analyze incident" })).toBeDisabled()
  expect(posts).toBe(1)
  finishSubmission(Response.json({ analysis_id: "job-1", incident_id: "missing-secret-01", status: "queued" }, { status: 202 }))
  expect(await screen.findByRole("alert")).toHaveTextContent("PROVIDER_FAILED")
})

test("analyze submits the incident currently shown in the overview", async () => {
  apiFetch("failed")
  const user = userEvent.setup()
  render(<App />)
  await screen.findByRole("heading", { name: "Scenario overview" })
  await user.click(screen.getByRole("button", { name: /Ad Service High CPU.*Demo-ready/ }))
  await screen.findByRole("heading", { name: "Ad Service High CPU" })
  await user.click(screen.getByRole("button", { name: "Analyze incident" }))
  expect(vi.mocked(fetch)).toHaveBeenCalledWith("/api/demo/analyses", expect.objectContaining({
    body: JSON.stringify({ incident_id: "ad-high-cpu-01" }),
  }))
})

test("experimental scenarios remain labeled while their prepared fixtures can be analyzed", async () => {
  const user = userEvent.setup()
  const nonReadyRows = structuredClone(incidents)
  const downstream = nonReadyRows.find((row) => row.id === "downstream-latency-01")!
  downstream.readiness = "experimental"
  const calls = apiFetch("failed", "KEEP_QUALIFIED", false, nonReadyRows)
  render(<App />)
  await screen.findByRole("heading", { name: "Scenario overview" })

  await user.click(screen.getByRole("button", { name: /Shipping Slowdown.*Experimental/ }))

  expect(screen.getByText("The average duration of Shipping's `ship-order` operation increases substantially, although its median duration rises much less.")).toBeInTheDocument()
  expect(screen.getByRole("button", { name: "Analyze incident" })).toBeEnabled()
  await user.click(screen.getByRole("button", { name: "Analyze incident" }))
  await waitFor(() => expect(calls).toContain("POST /api/demo/analyses"))
  expect(calls).toContain("GET /api/demo/analyses/job-1")
})
