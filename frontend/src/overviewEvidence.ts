import type { IncidentSnapshotItem } from "./contract"

export interface EvidenceSummary {
  service: string
  signal: string
  label: string
  details: string[]
}

type Fields = Record<string, unknown>

const metricNames: Record<string, string> = {
  container_memory_usage_bytes: "Container memory usage",
  container_memory_rss_bytes: "Resident memory",
  container_memory_available_bytes: "Available container memory",
  k8s_pod_cpu_usage: "Pod CPU usage",
  kafka_consumer_last_poll_seconds_ago: "Time since last Kafka poll",
  kafka_consumer_records_lag: "Kafka consumer lag",
  kafka_consumer_records_consumed_rate: "Records consumed per second",
  k8s_container_restarts: "Container restarts",
  rpc_server_call_duration_seconds_count: "RPC server request observation rate",
  rpc_client_call_duration_seconds_count: "RPC client response observation rate",
}

const operationNames: Record<string, string> = {
  send_email: "Send email latency",
  "POST /ship-order": "Ship-order latency",
  "POST /get-quote": "Shipping quote latency",
  "publish orders": "Publish orders latency",
  "oteldemo.CheckoutService/PlaceOrder": "Place order",
  "oteldemo.PaymentService/Charge": "Charge payment",
  "oteldemo.AdService/GetAds": "Get ads latency",
}

function fields(value: unknown): Fields {
  return value !== null && typeof value === "object" && !Array.isArray(value) ? value as Fields : {}
}

function string(value: unknown): string | null {
  return typeof value === "string" && value.trim() ? value : null
}

function number(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null
}

function readable(value: string): string {
  return value.replaceAll("_", " ").replaceAll("-", " ").replace(/\b\w/g, (letter) => letter.toUpperCase())
}

function format(value: number, digits = 2): string {
  return new Intl.NumberFormat("en", { maximumFractionDigits: digits }).format(value)
}

function metricSummary(value: Fields): Pick<EvidenceSummary, "label" | "details"> {
  const metric = string(value.metric)
  const label = metric ? metricNames[metric] ?? readable(metric) : "Metric observation"
  const rawUnit = string(value.unit)
  const bytes = rawUnit === "bytes"
  const histogramRate = value.metric_kind === "histogram_count" && rawUnit === "reported_unit/second"
  const unit = bytes ? "MiB"
    : histogramRate ? "observations/s"
      : metric === "kafka_consumer_last_poll_seconds_ago" ? "s"
        : rawUnit && !rawUnit.startsWith("reported_unit") && rawUnit !== "unknown" && rawUnit !== "1" ? rawUnit : ""
  const display = (n: number) => {
    const converted = bytes ? n / 1048576 : n
    const digits = bytes ? 2 : Math.abs(converted) < 0.01 && converted !== 0 ? 4 : 2
    return format(converted, digits) + (unit ? " " + unit : "")
  }
  const baseline = number(value.baseline_value)
  const incident = number(value.incident_value)
  const details: string[] = []
  if (baseline !== null && incident !== null) {
    details.push("Baseline " + display(baseline) + " → Incident " + display(incident))
  } else if (incident !== null) {
    details.push("Incident " + display(incident))
  } else if (baseline !== null) {
    details.push("Baseline " + display(baseline) + "; incident comparison unavailable")
  } else {
    details.push("Comparison unavailable")
  }
  const change = string(value.change)
  if (baseline !== null && incident !== null && change && ["increased", "decreased", "unchanged"].includes(change)) {
    details.push(readable(change))
  } else if (change === "appeared") {
    details.push("Series appeared during incident")
  } else if (change === "disappeared") {
    details.push("Series not observed during incident")
  }
  if (!unit && rawUnit?.startsWith("reported_unit")) details.push("Unit not specified")
  return { label, details }
}

function logName(value: Fields): string {
  const pattern = string(value.pattern) ?? string(value.example) ?? ""
  if (/invalid token/i.test(pattern)) return "Payment warning: invalid token"
  if (/connect to redis/i.test(pattern)) return "Storage connection error"
  if (/high cpu/i.test(pattern)) return "High CPU load log pattern"
  if (/sleeping 1 second/i.test(pattern)) return "Consumer processing pause"
  if (/overloading queue/i.test(pattern)) return "Queue processing message"
  if (/payment went through|transaction complete/i.test(pattern)) return "Successful payment completion"
  return string(value.severity) ? readable(string(value.severity)!) + " log pattern" : "Log pattern"
}

function logSummary(value: Fields): Pick<EvidenceSummary, "label" | "details"> {
  const baseline = number(value.baseline_count)
  const incident = number(value.incident_count)
  let comparison = "Comparison unavailable"
  if (baseline !== null && incident !== null) {
    comparison = baseline === 0
      ? "Not observed in baseline → " + format(incident, 0) + " occurrences during incident"
      : incident === 0
        ? format(baseline, 0) + " occurrences at baseline → not observed during incident"
        : format(baseline, 0) + " → " + format(incident, 0) + " occurrences"
  }
  return { label: logName(value), details: [comparison] }
}

function traceSummary(value: Fields): Pick<EvidenceSummary, "label" | "details"> {
  const operation = string(value.operation_or_callee)
  const boundary = Array.isArray(value.uncertainty)
    && value.uncertainty.some((entry) => entry === "boundary_attribution_uncertain" || entry === "excluded_from_window_aggregates")
  const label = boundary && operation?.includes("EmptyCart") ? "EmptyCart operation"
    : operation && operationNames[operation] ? operationNames[operation]
      : value.kind === "edge" && operation ? "Call to " + readable(operation) + " latency"
        : operation ? readable(operation) + " latency" : "Trace operation"
  if (boundary) {
    return {
      label,
      details: [
        ...(value.boundary_error === true ? ["Failed operation observed at window boundary"] : []),
        "Comparison unavailable (window attribution uncertain)",
      ],
    }
  }
  const details: string[] = []
  for (const [name, key] of [["Mean", "mean"], ["Median", "median"]] as const) {
    const baseline = number(value["baseline_" + key + "_ms"])
    const incident = number(value["incident_" + key + "_ms"])
    if (baseline !== null && incident !== null) {
      details.push(name + " " + format(baseline) + " ms → " + format(incident) + " ms")
    } else if (incident !== null) {
      details.push(name + " during incident: " + format(incident) + " ms")
    }
  }
  if (!details.length) details.push("Comparison unavailable")
  const beforeErrors = number(value.baseline_errors)
  const duringErrors = number(value.incident_errors)
  if (beforeErrors !== null && duringErrors !== null) {
    details.push(beforeErrors === 0 && duringErrors === 0
      ? "No operation errors recorded"
      : "Errors " + format(beforeErrors, 0) + " → " + format(duringErrors, 0))
  }
  return { label, details }
}

function kubernetesSummary(value: Fields): Pick<EvidenceSummary, "label" | "details"> {
  const eventReason = string(value.event_reason)
  if (eventReason) {
    const message = string(value.event_message) ?? ""
    const details = [
      eventReason === "Failed" && /secret.*not found/i.test(message)
        ? "Required Secret not found" : eventReason === "BackOff"
          ? "Restart backoff recorded" : "Kubernetes event recorded",
    ]
    const count = number(value.event_count)
    if (count !== null) details.push(format(count, 0) + " recorded events (cumulative)")
    return { label: "Kubernetes event: " + eventReason, details }
  }
  const state = string(value.container_state)
  const details = state ? ["State: " + readable(state)] : []
  const reason = string(value.waiting_reason) ?? string(value.termination_reason)
  if (reason) details.push("Reason: " + reason)
  const phase = string(value.phase)
  if (phase) details.push("Pod: " + phase)
  const exitCode = number(value.exit_code)
  const restarts = number(value.restart_count)
  if (exitCode !== null && restarts !== null) details.push("Exit code: " + format(exitCode, 0) + " · Restart count: " + format(restarts, 0))
  else if (restarts !== null && restarts > 0) details.push("Restart count: " + format(restarts, 0))
  if (value.ready === false) details.push("Not ready")
  else if (value.ready === true) details.push("Ready")
  return { label: "Container state", details: details.length ? details : ["Comparison unavailable"] }
}

export function summarizeEvidence(item: IncidentSnapshotItem): EvidenceSummary {
  const value = fields(item.presentation.raw.value)
  const owner = string(value.service) ?? string(value.deployment) ?? string(item.presentation.source_service) ?? "Unknown component"
  const signal = item.presentation.signal_type
  const summary = signal === "metric" ? metricSummary(value)
    : signal === "log" ? logSummary(value)
      : signal === "trace" ? traceSummary(value)
        : kubernetesSummary(value)
  return {
    service: owner === "Unknown component" ? owner : readable(owner),
    signal: signal === "metric" ? "Metric" : signal === "log" ? "Log" : signal === "trace" ? "Trace" : "Kubernetes",
    ...summary,
  }
}
