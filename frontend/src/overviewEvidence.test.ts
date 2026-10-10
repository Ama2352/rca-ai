import { expect, test } from "vitest"
import type { EvidenceSignal, IncidentSnapshotItem } from "./contract"
import { summarizeEvidence } from "./overviewEvidence"
import missing from "../../data/demo/missing-secret-01.json"
import application from "../../data/demo/application-failure-01.json"
import ad from "../../data/demo/ad-high-cpu-01.json"
import cart from "../../data/demo/cart-failure-01.json"
import shipping from "../../data/demo/downstream-latency-01.json"
import memory from "../../data/demo/memory-leak-01.json"
import messaging from "../../data/demo/messaging-failure-01.json"
import crash from "../../data/demo/crash-loop-backoff-01.json"

type Observation = {
  observation_id: string
  signal: string
  entity: { type: string; id: string }
  field: string
  value: unknown
  source: { source_ref: string; source_path: string }
}
type Fixture = { evidence: { observations: Observation[] } }

function snapshot(fixture: Fixture, id: string): IncidentSnapshotItem {
  const observation = fixture.evidence.observations.find((row) => row.observation_id === id)
  if (!observation) throw new Error(`Missing fixture observation: ${id}`)
  const fact = {
    fact_id: "F1", entity: observation.entity, field: observation.field,
    value: observation.value, source_ref: observation.source.source_ref,
    source_path: observation.source.source_path,
  }
  return {
    observation_id: id, source_ref: observation.source.source_ref,
    presentation: {
      id: "F1", signal_type: observation.signal as EvidenceSignal, title: "Technical title",
      statistic_kind: null, baseline: null, incident: null, unit: null, change: null,
      source_service: null, destination_service: null, operation: null, severity: null,
      state: null, preview: null, technical: {}, raw: fact,
    },
  }
}

test("Kubernetes state and event remain separate readable observations", () => {
  const state = summarizeEvidence(snapshot(missing, "a85a7eff00aa98136235be9e"))
  const event = summarizeEvidence(snapshot(missing, "d5563ffafe9100e99220be7f"))
  expect(state).toMatchObject({
    service: "Telemetry Docs", signal: "Kubernetes", label: "Container state",
    details: expect.arrayContaining(["State: Waiting", "Reason: CreateContainerConfigError", "Pod: Pending", "Not ready"]),
  })
  expect(event).toMatchObject({
    service: "Telemetry Docs", signal: "Kubernetes", label: "Kubernetes event: Failed",
  })
  expect(event.details.join(" ")).toMatch(/Secret.*not found/)
  expect(JSON.stringify([state, event])).not.toMatch(/a85a7eff|d5563ffa|source_ref|pod_uid/)
})

test("Payment invalid-token log shows observed occurrence counts", () => {
  expect(summarizeEvidence(snapshot(application, "823d2b475830b7bac53f7246"))).toEqual({
    service: "Payment", signal: "Log", label: "Payment warning: invalid token",
    details: ["Not observed in baseline → 6 occurrences during incident"],
  })
})

test("Ad CPU retains the reported-unit uncertainty and trace does not claim degradation", () => {
  const cpu = summarizeEvidence(snapshot(ad, "310cbe59d2d0675e021d9ef1"))
  expect(cpu.label).toBe("Pod CPU usage")
  expect(cpu.details).toContain("Baseline 0.0053 → Incident 2.49")
  expect(cpu.details).toContain("Unit not specified")
  expect(cpu.details.join(" ")).not.toMatch(/%|percent/)
  const trace = summarizeEvidence(snapshot(ad, "0cad6ea9e3fa4c21136334c4"))
  expect(trace.details.join(" ")).not.toMatch(/increased|degraded/i)
})

test("Cart boundary trace does not turn a boundary duration into a window comparison", () => {
  const row = summarizeEvidence(snapshot(cart, "e1732a19ec990fb481af4520"))
  expect(row.label).toContain("EmptyCart")
  expect(row.details).toContain("Failed operation observed at window boundary")
  expect(row.details).toContain("Comparison unavailable (window attribution uncertain)")
  expect(row.details.join(" ")).not.toMatch(/90,?862|mean|median/i)
})

test("Shipping trace compares mean with mean and median with median", () => {
  const row = summarizeEvidence(snapshot(shipping, "f7182f3b9b1e689770d30c83"))
  expect(row).toMatchObject({ service: "Shipping", signal: "Trace", label: "Ship-order latency" })
  expect(row.details).toContain("Mean 0.82 ms → 1,670.5 ms")
  expect(row.details).toContain("Median 0.82 ms → 2.86 ms")
  expect(row.details).toContain("No operation errors recorded")
})

test("Memory byte values display as MiB without changing the raw observation", () => {
  const input = snapshot(memory, "ff12bca38ca471504045495e")
  const original = JSON.stringify(input)
  const row = summarizeEvidence(input)
  expect(row).toMatchObject({ service: "Email", signal: "Metric", label: "Resident memory" })
  expect(row.details).toContain("Baseline 48.78 MiB → Incident 63.92 MiB")
  expect(JSON.stringify(input)).toBe(original)
})

test("Messaging lag remains at zero and the pause log is readable", () => {
  const lag = summarizeEvidence(snapshot(messaging, "0968ce5e8ae92d29ff27bd68"))
  expect(lag.label).toBe("Kafka consumer lag")
  expect(lag.details).toContain("Baseline 0 → Incident 0")
  expect(lag.details).toContain("Unchanged")
  const pause = summarizeEvidence(snapshot(messaging, "5db48f63cc31148449f4ae55"))
  expect(pause.label).toBe("Consumer processing pause")
  expect(pause.details).toContain("Not observed in baseline → 101 occurrences during incident")
})

test("Crash state reports termination and restart count without borrowing event fields", () => {
  const state = summarizeEvidence(snapshot(crash, "a85a7eff00aa98136235be9e"))
  expect(state.details).toEqual(expect.arrayContaining(["State: Terminated", "Exit code: 42 · Restart count: 3", "Not ready"]))
  const event = summarizeEvidence(snapshot(crash, "35d8fd27bfcaa31f175ed000"))
  expect(event.label).toBe("Kubernetes event: BackOff")
  expect(event.details.join(" ")).not.toContain("Exit code")
})

test("missing numeric windows show a neutral state", () => {
  const input = snapshot(memory, "ff12bca38ca471504045495e")
  input.presentation.raw.value = { service: "email", metric: "container_memory_rss_bytes", unit: "bytes" }
  const row = summarizeEvidence(input)
  expect(row.details).toContain("Comparison unavailable")
  expect(row.details.join(" ")).not.toMatch(/NaN|undefined|→/)
})

test("unknown component does not expose an observation-like entity ID", () => {
  const input = snapshot(memory, "ff12bca38ca471504045495e")
  input.presentation.raw.entity.id = "343c82e331b11eb13a460931"
  input.presentation.raw.value = { metric: "container_memory_rss_bytes", unit: "bytes" }
  const row = summarizeEvidence(input)
  expect(row.service).toBe("Unknown component")
  expect(JSON.stringify(row)).not.toContain("343c82e331b11eb13a460931")
})
