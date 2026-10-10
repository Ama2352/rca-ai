import { afterEach, beforeEach, expect, test, vi } from "vitest"
import "@testing-library/jest-dom/vitest"
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import PreparedJsonViewer from "./PreparedJsonViewer"
import missing from "../../data/demo/missing-secret-01.json"
import application from "../../data/demo/application-failure-01.json"
import ad from "../../data/demo/ad-high-cpu-01.json"
import cart from "../../data/demo/cart-failure-01.json"
import dependency from "../../data/demo/dependency-unavailable-01.json"
import shipping from "../../data/demo/downstream-latency-01.json"
import memory from "../../data/demo/memory-leak-01.json"
import messaging from "../../data/demo/messaging-failure-01.json"
import crash from "../../data/demo/crash-loop-backoff-01.json"

const fixtures = {
  "missing-secret-01": missing,
  "application-failure-01": application,
  "ad-high-cpu-01": ad,
  "cart-failure-01": cart,
  "dependency-unavailable-01": dependency,
  "downstream-latency-01": shipping,
  "memory-leak-01": memory,
  "messaging-failure-01": messaging,
  "crash-loop-backoff-01": crash,
}

beforeEach(() => {
  HTMLDialogElement.prototype.showModal = function () { this.setAttribute("open", "") }
  HTMLDialogElement.prototype.close = function () {
    this.removeAttribute("open")
    this.dispatchEvent(new Event("close"))
  }
})
afterEach(() => { cleanup(); vi.unstubAllGlobals() })

test.each(Object.entries(fixtures))("viewer renders complete prepared input for %s", async (id, fixture) => {
  const request = vi.fn(async () => Response.json(fixture))
  vi.stubGlobal("fetch", request)
  render(<PreparedJsonViewer incidentId={id} onClose={() => {}} />)
  const dialog = screen.getByRole("dialog", { name: /Prepared canonical JSON/ })
  await waitFor(() => expect(dialog.querySelector("pre")).not.toBeNull())
  const shown = JSON.parse(dialog.querySelector("pre")!.textContent!)
  expect(shown).toEqual(fixture)
  expect(shown.evidence.observations).toHaveLength(fixture.evidence.observations.length)
  expect(request).toHaveBeenCalledWith(`/api/demo/incidents/${id}/prepared-input`)
})

test("viewer reloads the selected scenario and copies the original response", async () => {
  const raw = JSON.stringify(missing)
  vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) =>
    new Response(String(input).includes("ad-high-cpu") ? JSON.stringify(ad) : raw, {
      headers: { "Content-Type": "application/json" },
    })))
  const writeText = vi.fn(async () => {})
  const user = userEvent.setup()
  Object.defineProperty(navigator, "clipboard", { configurable: true, value: { writeText } })
  const { rerender } = render(<PreparedJsonViewer incidentId="missing-secret-01" onClose={() => {}} />)
  await screen.findByText(/"incident_id": "missing-secret-01"/)
  await user.click(screen.getByRole("button", { name: "Copy JSON" }))
  expect(writeText).toHaveBeenCalledWith(raw)
  rerender(<PreparedJsonViewer incidentId="ad-high-cpu-01" onClose={() => {}} />)
  await screen.findByText(/"incident_id": "ad-high-cpu-01"/)
  expect(screen.getByRole("dialog").querySelector("pre")?.textContent).not.toContain('"incident_id": "missing-secret-01"')
})

test("viewer exposes loading, failure, close button, and keyboard dismissal", async () => {
  let reject!: (error: Error) => void
  const pending = new Promise<Response>((_resolve, rejectPromise) => { reject = rejectPromise })
  vi.stubGlobal("fetch", vi.fn(() => pending))
  const onClose = vi.fn()
  render(<PreparedJsonViewer incidentId="missing-secret-01" onClose={onClose} />)
  expect(screen.getByRole("status")).toHaveTextContent("Loading prepared JSON")
  reject(new Error("backend unavailable"))
  expect(await screen.findByRole("alert")).toHaveTextContent("backend unavailable")
  fireEvent(screen.getByRole("dialog"), new Event("cancel", { bubbles: true, cancelable: true }))
  expect(onClose).toHaveBeenCalled()
  await userEvent.setup().click(screen.getByRole("button", { name: "Close prepared JSON" }))
  expect(onClose).toHaveBeenCalledTimes(2)
})
