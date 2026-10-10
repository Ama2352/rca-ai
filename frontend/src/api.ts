import type { AnalysisJob, DemoIncident } from "./contract"

async function readJson<T>(response: Response): Promise<T> {
  if (!response.ok) {
    let message = `Demo API returned HTTP ${response.status}`
    try {
      const body = await response.json() as { detail?: string }
      if (body.detail) message = body.detail
    } catch { /* The HTTP status remains useful if no JSON body is available. */ }
    throw new Error(message)
  }
  return response.json() as Promise<T>
}

export async function listIncidents(): Promise<DemoIncident[]> {
  const body = await readJson<{ incidents: DemoIncident[] }>(await fetch("/api/demo/incidents"))
  return body.incidents
}

export async function getPreparedInput(incidentId: string): Promise<string> {
  const response = await fetch(`/api/demo/incidents/${encodeURIComponent(incidentId)}/prepared-input`)
  if (!response.ok) {
    await readJson<never>(response)
    throw new Error(`Demo API returned HTTP ${response.status}`)
  }
  return response.text()
}

export async function startAnalysis(incidentId: string): Promise<AnalysisJob> {
  return readJson<AnalysisJob>(await fetch("/api/demo/analyses", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ incident_id: incidentId }),
  }))
}

export async function getAnalysis(analysisId: string): Promise<AnalysisJob> {
  return readJson<AnalysisJob>(await fetch(`/api/demo/analyses/${encodeURIComponent(analysisId)}`))
}
