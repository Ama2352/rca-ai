import { afterEach, expect, test, vi } from "vitest"
import "@testing-library/jest-dom/vitest"
import { cleanup, render, screen, waitFor, within } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import App from "./App"
import type { AnalysisJob, Fact } from "./contract"

afterEach(() => { cleanup(); vi.unstubAllGlobals() })

const incidents = [
  { id: "missing-secret-01", title: "Telemetry Docs — Startup Failure", description: "The telemetry-docs pod is Pending while its container is waiting to start; a separate observation reports Running.",
    source: "custom-k8s", readiness: "demo-ready", prepared_input: "data/demo/missing-secret-01.json",
    affected_services: ["telemetry-docs"], symptoms: ["Pending pod"],
    available_evidence_sources: ["kubernetes"], analysis_mode: "Evidence-grounded RCA",
    investigation_focus: ["Inspect Kubernetes state", "Validate explanations"],
    incident_snapshot: [{ observation_id: "observation-one", source_ref: "source-one", presentation: {
      id: "F1", signal_type: "kubernetes", title: "Telemetry Docs · Pending", statistic_kind: null,
      baseline: null, incident: null, unit: null, change: null, source_service: null,
      destination_service: null, operation: null, severity: null, state: "Pending", preview: null,
      technical: { source_ref: "source-one" }, raw: { value: { phase: "Pending" } },
    } }] },
  { id: "application-failure-01", title: "Checkout and Payment — Application Failure",
    source: "otel-demo", readiness: "demo-ready", prepared_input: "data/demo/application-failure-01.json",
    description: "Checkout PlaceOrder failures and Payment Charge errors are observed during the incident window.", affected_services: ["checkout", "payment"],
    symptoms: ["Operation errors"], available_evidence_sources: ["metric", "log", "trace", "kubernetes"],
    analysis_mode: "Evidence-grounded RCA", investigation_focus: ["Inspect traces", "Validate explanations"] },
  { id: "ad-high-cpu-01", title: "Ad Service — High CPU", description: "Ad service CPU measurements rise sharply during the incident window.",
    source: "otel-demo", readiness: "demo-ready", prepared_input: "data/demo/ad-high-cpu-01.json",
    affected_services: ["ad"], symptoms: ["Elevated CPU"],
    available_evidence_sources: ["metric", "log", "trace", "kubernetes"],
    analysis_mode: "Evidence-grounded RCA", investigation_focus: ["Compare CPU", "Validate explanations"] },
  { id: "dependency-unavailable-01", title: "Checkout → Payment · Dependency Unavailable", description: "Checkout records UNAVAILABLE responses on outbound Payment Charge requests.",
    source: "otel-demo", readiness: "demo-ready", prepared_input: "data/demo/dependency-unavailable-01.json",
    affected_services: ["checkout", "payment"], symptoms: ["UNAVAILABLE responses"], available_evidence_sources: ["metric", "log", "trace", "kubernetes"],
    analysis_mode: "Evidence-grounded RCA", investigation_focus: ["Inspect dependency edge"] },
  { id: "messaging-failure-01", title: "Messaging Failure", description: "A prepared queue-overload simulation and consumer delay are captured.",
    source: "otel-demo", readiness: "demo-ready", prepared_input: "data/demo/messaging-failure-01.json",
    affected_services: ["checkout", "fraud-detection", "kafka"], symptoms: ["Consumer delay", "zero measured lag"],
    available_evidence_sources: ["metric", "log", "trace", "kubernetes"], analysis_mode: "Evidence-grounded RCA", investigation_focus: ["Inspect messaging signals"] },
  ...[
    ["cart-failure-01", "Cart Failure", "otel-demo"],
    ["downstream-latency-01", "Downstream Latency", "otel-demo"],
    ["memory-leak-01", "Memory Leak", "otel-demo"],
    ["crash-loop-backoff-01", "Crash Loop Backoff", "custom-k8s"],
  ].map(([id, title, source]) => ({ id, title, source, readiness: "experimental", prepared_input: null })),
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
) {
  const calls: string[] = []
  const fetcher = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input)
    calls.push(`${init?.method ?? "GET"} ${url}`)
    if (url === "/api/demo/incidents") return Response.json({ incidents })
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
  expect(screen.getByText("Kubernetes", { exact: true })).toBeInTheDocument()
  expect(screen.getByRole("heading", { name: "Scenario Library" })).toBeInTheDocument()
  expect(screen.getByRole("heading", { name: "OpenTelemetry Demo" })).toBeInTheDocument()
  expect(screen.getByRole("heading", { name: "Custom Kubernetes" })).toBeInTheDocument()
  expect(screen.getAllByRole("button", { name: /Demo v1 analysis available/ })).toHaveLength(5)
  expect(screen.getAllByRole("button", { name: /Not yet available for Demo v1 analysis/ })).toHaveLength(4)
  expect(screen.getByText(/Telemetry is observation, not a confirmed root cause/i)).toBeInTheDocument()
  expect(screen.queryByText("A cautious working explanation.")).not.toBeInTheDocument()
  expect(calls).toEqual(["GET /api/demo/incidents"])
})

test("known cause, observed symptoms, and RCA explanation are separate before analysis", async () => {
  apiFetch()
  render(<App />)
  expect(await screen.findByRole("heading", { name: "Known scenario cause" })).toBeInTheDocument()
  expect(screen.getByRole("heading", { name: "Observed symptoms" })).toBeInTheDocument()
  expect(screen.getByText(/required environment-variable reference was added.*Secret verified absent/i)).toBeInTheDocument()
  expect(screen.getByText(/A different telemetry-docs pod was Running and Ready in the same snapshot/i)).toBeInTheDocument()
  expect(screen.queryByText(/Telemetry-Docs · Pending · Pending/)).not.toBeInTheDocument()
  expect(screen.getByText(/RCA reviews current evidence/i)).toBeInTheDocument()
  expect(screen.queryByText("A cautious working explanation.")).not.toBeInTheDocument()
})

test.each([
  ["Checkout → Payment · Dependency Unavailable", "paymentUnreachable", /outbound Payment Charge metric records incident responses labeled UNAVAILABLE/],
  ["Messaging Failure", "kafkaQueueProblems", /measured consumer-lag metric stays at 0/],
])("new scenario overview shows its cause and qualified symptoms before analysis", async (title, flag, symptom) => {
  const calls = apiFetch()
  const user = userEvent.setup()
  render(<App />)
  await screen.findByRole("heading", { name: "Scenario overview" })
  await user.click(screen.getByRole("button", { name: new RegExp(`${title}.*Demo v1 analysis available`) }))
  expect(screen.getByText(new RegExp(flag))).toBeInTheDocument()
  expect(screen.getByText(symptom)).toBeInTheDocument()
  expect(screen.getByText("Available telemetry")).toBeInTheDocument()
  expect(screen.getByRole("button", { name: "Analyze incident" })).toBeEnabled()
  expect(calls).toEqual(["GET /api/demo/incidents"])
})

test("semantic Fact rendering shows meaning before collapsed raw JSON", async () => {
  apiFetch()
  const user = userEvent.setup()
  render(<App />)
  await screen.findByText(/A replacement telemetry-docs pod was Pending/i)
  await user.click(screen.getByRole("button", { name: "Analyze incident" }))
  expect(await screen.findByRole("heading", { name: "Telemetry Docs · Pending" })).toBeInTheDocument()
  expect(screen.queryByText("null → null")).not.toBeInTheDocument()
  expect(screen.getByText("View technical source")).toBeInTheDocument()
  expect(screen.queryByText("View raw JSON")).not.toBeInTheDocument()
})

test.each([
  ["missing-secret-01", /required environment-variable reference was added.*Secret verified absent/i, /replacement telemetry-docs pod was Pending/i, ["Kubernetes"]],
  ["application-failure-01", /paymentFailure.*selected share of Payment/i, /Payment WARN logs appeared 6 times.*Invalid token/i, ["Metrics", "Logs", "Traces", "Kubernetes"]],
  ["ad-high-cpu-01", /adHighCpu.*triggering high CPU load/i, /CPU-usage metric rose sharply.*concrete unit/i, ["Metrics", "Logs", "Traces", "Kubernetes"]],
])("scenario overview separates the verified cause from observed symptoms for %s", async (id, cause, symptom, telemetry) => {
  apiFetch()
  const user = userEvent.setup()
  render(<App />)
  await screen.findByRole("heading", { name: "Scenario overview" })
  if (id !== "missing-secret-01") {
    const title = id === "application-failure-01" ? /Checkout and Payment/ : /Ad Service — High CPU/
    await user.click(screen.getByRole("button", { name: new RegExp(String(title.source) + ".*Demo v1 analysis available") }))
  }
  const causeHeading = screen.getByRole("heading", { name: "Known scenario cause" })
  const causeSection = causeHeading.closest("section")!
  expect(within(causeSection).getByText(cause)).toBeInTheDocument()
  expect(screen.getByRole("heading", { name: "Observed symptoms" })).toBeInTheDocument()
  expect(screen.getByText(symptom)).toBeInTheDocument()
  expect(causeSection.compareDocumentPosition(screen.getByRole("button", { name: "Analyze incident" })) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
  expect(screen.getByText("Available telemetry")).toBeInTheDocument()
  for (const badge of telemetry) expect(screen.getByText(badge, { exact: true })).toBeInTheDocument()
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
  await screen.findByText(/A replacement telemetry-docs pod was Pending/i)
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
      stage_label: "Validating hypotheses", error: { code: "PROVIDER_FAILED" },
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
  expect(await screen.findByRole("alert", {}, { timeout: 3500 })).toHaveTextContent("PROVIDER_FAILED")
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
  await screen.findByText(/A replacement telemetry-docs pod was Pending/i)
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
  await screen.findByText(/A replacement telemetry-docs pod was Pending/i)
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
  await screen.findByText(/A replacement telemetry-docs pod was Pending/i)
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
      stage: "validation", stage_label: "Waiting for provider pacing", candidate_id: "HYP1",
      completed_stages: [{ stage: "preparation", seconds: 0.1 }, { stage: "evidence", seconds: 0.2 },
        { stage: "retrieval", seconds: 0.3 }, { stage: "generation", seconds: 0.6 }],
      elapsed_seconds: 10,
    }))
    throw new Error(`Unexpected request: ${url}`)
  }))
  const user = userEvent.setup()
  render(<App />)
  await screen.findByText(/A replacement telemetry-docs pod was Pending/i)
  await user.click(screen.getByRole("button", { name: "Analyze incident" }))
  expect(await screen.findByText("Waiting for provider pacing")).toBeInTheDocument()
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
  await screen.findByText(/A replacement telemetry-docs pod was Pending/i)
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
  await screen.findByText(/A replacement telemetry-docs pod was Pending/i)
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
  await screen.findByText(/A replacement telemetry-docs pod was Pending/i)
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
  await screen.findByText(/A replacement telemetry-docs pod was Pending/i)
  await user.click(screen.getByRole("button", { name: "Analyze incident" }))
  expect(await screen.findByText("No explanatory candidate was retained.")).toBeInTheDocument()
  expect(screen.queryByRole("alert")).not.toBeInTheDocument()
})

test("switching incidents updates overview and clears the prior analysis", async () => {
  apiFetch()
  const user = userEvent.setup()
  render(<App />)
  await screen.findByText(/A replacement telemetry-docs pod was Pending/i)
  await user.click(screen.getByRole("button", { name: "Analyze incident" }))
  await screen.findByText("A cautious working explanation.")
  await user.click(screen.getByRole("button", { name: /Ad Service — High CPU.*Demo v1 analysis available/ }))
  expect(await screen.findByText(/Ad pod's CPU-usage metric rose sharply/i)).toBeInTheDocument()
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
  await screen.findByText(/A replacement telemetry-docs pod was Pending/i)
  await user.click(screen.getByRole("button", { name: "Analyze incident" }))
  expect(await screen.findByRole("status")).toHaveTextContent("Analysis")
  await user.click(screen.getByRole("button", { name: /Ad Service — High CPU.*Demo v1 analysis available/ }))
  finishOldJob(Response.json(completed))
  expect(await screen.findByText(/Ad pod's CPU-usage metric rose sharply/i)).toBeInTheDocument()
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
  await screen.findByText(/A replacement telemetry-docs pod was Pending/i)
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
  await screen.findByText(/A replacement telemetry-docs pod was Pending/i)
  await user.click(screen.getByRole("button", { name: /Ad Service — High CPU.*Demo v1 analysis available/ }))
  await screen.findByText(/Ad pod's CPU-usage metric rose sharply/i)
  await user.click(screen.getByRole("button", { name: "Analyze incident" }))
  expect(vi.mocked(fetch)).toHaveBeenCalledWith("/api/demo/analyses", expect.objectContaining({
    body: JSON.stringify({ incident_id: "ad-high-cpu-01" }),
  }))
})

test("experimental scenarios can be selected but never submitted for analysis", async () => {
  const calls = apiFetch("failed")
  const user = userEvent.setup()
  render(<App />)
  await screen.findByText(/A replacement telemetry-docs pod was Pending/i)

  await user.click(screen.getByRole("button", { name: /Cart Failure.*Not yet available for Demo v1 analysis/ }))

  expect(screen.getAllByText("Captured for research; not yet validated for Demo v1.")).toHaveLength(1)
  expect(screen.getByRole("button", { name: "Analyze incident" })).toBeDisabled()
  expect(calls).toEqual(["GET /api/demo/incidents"])
})
