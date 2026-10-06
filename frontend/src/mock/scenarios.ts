import adResult from "./ad-high-cpu-01/rca-result.json"
import adSources from "./ad-high-cpu-01/resolved-sources.json"
import appResult from "./application-failure-01/rca-result.json"
import appSources from "./application-failure-01/resolved-sources.json"
import abstentionResult from "./abstention/rca-result.json"
import abstentionSources from "./abstention/resolved-sources.json"
import secretResult from "./missing-secret-01/rca-result.json"
import secretSources from "./missing-secret-01/resolved-sources.json"
import type { RCAResult, ResolvedSources } from "../contract"

export interface DemoScenario {
  id: string
  label: string
  result: RCAResult
  resolvedSources: ResolvedSources[]
  preview?: boolean
}

const fixture = (
  id: string,
  label: string,
  result: RCAResult,
  resolvedSources: ResolvedSources[],
  preview = false,
): DemoScenario => ({ id, label, result, resolvedSources, preview })

const secret = secretResult as RCAResult
const secretResolved = secretSources as ResolvedSources[]

export const scenarios: DemoScenario[] = [
  fixture("missing-secret", "Missing Secret", secret, secretResolved),
  fixture("application-failure", "Application Failure", appResult as RCAResult, appSources as ResolvedSources[]),
  fixture("ad-high-cpu", "Ad High CPU", adResult as RCAResult, adSources as ResolvedSources[]),
  fixture(
    "secret-two-candidates",
    "Missing Secret · two-candidate state",
    { ...secret, candidate_results: secret.candidate_results.slice(0, 2) },
    secretResolved.slice(0, 2),
    true,
  ),
  fixture(
    "secret-one-candidate",
    "Missing Secret · one-candidate state",
    { ...secret, candidate_results: secret.candidate_results.slice(0, 1) },
    secretResolved.slice(0, 1),
    true,
  ),
  fixture("abstention", "Abstention · empty contract state", abstentionResult as RCAResult, abstentionSources as ResolvedSources[], true),
]
