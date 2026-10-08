import { useEffect, useRef, useState } from "react"
import {
  ChevronDown,
  CircleDot,
  FileSearch,
} from "lucide-react"
import {
  Badge,
} from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible"
import { Separator } from "@/components/ui/separator"
import {
  Tabs,
  TabsList,
  TabsTrigger,
} from "@/components/ui/tabs"
import type { AnalysisJob, CandidateResult, DemoIncident, EvidencePresentation, EvidenceSignal, Fact, RCAResult, ResolvedSources, SupportLevel } from "./contract"
import { getAnalysis, listIncidents, startAnalysis } from "./api"

const supportLabels: Record<SupportLevel, string> = {
  STRONG: "Strong",
  PLAUSIBLE: "Plausible",
  WEAK: "Weak",
  CONTRADICTED: "Contradicted",
}

function decisionLabel(candidate: CandidateResult) {
  return candidate.analysis.decision === "KEEP_QUALIFIED"
    ? "Kept with qualification"
    : "Kept"
}

const statisticLabels: Record<string, string> = {
  median_latency: "Median latency",
  average_latency: "Average latency",
  occurrences: "Occurrences",
  histogram_observation_rate: "Histogram observation rate",
  histogram_observation_count: "Histogram observation count",
  rate: "Rate",
  error_count: "Error count",
  error_rate: "Error rate",
  value: "Value",
}

export function formatDuration(seconds: number) {
  if (!Number.isFinite(seconds) || seconds <= 0) return "0 ms"
  if (seconds < 1) return `${Math.max(1, Math.round(seconds * 1000))} ms`
  const rounded = Math.round(seconds)
  if (rounded < 60) return `${seconds.toFixed(seconds < 10 ? 1 : 0).replace(/\.0$/, "")}s`
  const minutes = Math.floor(rounded / 60)
  const remainder = rounded % 60
  return `${minutes}m ${remainder}s`
}

function formatMeasure(value: number, unit: string | null) {
  const amount = new Intl.NumberFormat("en", { maximumFractionDigits: 4 }).format(value)
  return unit && unit !== "1" ? `${amount} ${unit}` : amount
}

function sourceTarget(candidateId: string, kind: "F" | "H" | "K", id: string) {
  return `source-${candidateId}-${kind}-${id}`
}

function ReferenceChip({ id, kind, candidateId, exists }: {
  id: string; kind: "F" | "H" | "K"; candidateId: string; exists: boolean
}) {
  if (!exists) return <span className="unresolved-ref" title="unresolved in this result">{id} · unresolved in this result</span>
  function navigate() {
    const target = document.getElementById(sourceTarget(candidateId, kind, id))
    if (!target) return
    target.scrollIntoView?.({ behavior: "smooth", block: "center" })
    target.classList.add("is-reference-target")
    window.setTimeout(() => target.classList.remove("is-reference-target"), 1800)
  }
  return <button type="button" className="reference-chip" onClick={navigate}>{id}</button>
}

function FactCard({ fact, presentation, candidateId }: { fact: Fact; presentation: EvidencePresentation; candidateId: string }) {
  const paired = presentation.baseline !== null && presentation.incident !== null
  const status = presentation.change === "appeared"
    ? "Appeared during incident"
    : presentation.change === "disappeared"
      ? "Disappeared during incident"
      : null
  return (
    <article className="fact-row" id={sourceTarget(candidateId, "F", fact.fact_id)}>
      <div className="fact-copy">
        <div className="fact-heading">
          <h4>{presentation.title}</h4>
          <span className="fact-id">{fact.fact_id}</span>
        </div>
        {status && <p className="fact-observation">{status}</p>}
        {paired && presentation.statistic_kind && (
          <div className="change-line">
            <p className="change-caption">{statisticLabels[presentation.statistic_kind] ?? "Value"} · baseline → incident</p>
            <div className="change-values">
              <span>{formatMeasure(presentation.baseline!, presentation.unit)}</span>
              <span className="change-arrow" aria-label="to">→</span>
              <strong>{formatMeasure(presentation.incident!, presentation.unit)}</strong>
            </div>
          </div>
        )}
        {!paired && !status && presentation.incident !== null && (
          <p className="fact-observation">{formatMeasure(presentation.incident, presentation.unit)} during incident</p>
        )}
        {!paired && !status && presentation.incident === null && presentation.baseline === null && presentation.state && (
          <p className="fact-observation">{presentation.state}</p>
        )}
        {presentation.preview && <p className="fact-observation">{presentation.preview}</p>}
        {(presentation.source_service || presentation.destination_service || presentation.operation || presentation.severity) && (
          <dl className="fact-attributes">
            {presentation.source_service && <div><dt>Service</dt><dd>{presentation.source_service}</dd></div>}
            {presentation.destination_service && <div><dt>Destination</dt><dd>{presentation.destination_service}</dd></div>}
            {presentation.operation && <div><dt>Operation</dt><dd>{presentation.operation}</dd></div>}
            {presentation.severity && <div><dt>Severity</dt><dd>{presentation.severity}</dd></div>}
          </dl>
        )}
        <Collapsible className="source-details" defaultOpen={false}>
          <CollapsibleTrigger className="details-trigger">
            View technical source <ChevronDown aria-hidden="true" />
          </CollapsibleTrigger>
          <CollapsibleContent className="details-content">
            <dl className="source-metadata">
              <div><dt>Signal</dt><dd>{presentation.signal_type}</dd></div>
              <div><dt>Fact</dt><dd>{fact.fact_id}</dd></div>
              <div><dt>Source</dt><dd>{fact.source_ref}</dd></div>
              <div><dt>Source path</dt><dd>{fact.source_path}</dd></div>
              <div><dt>Entity</dt><dd>{fact.entity.type} / {fact.entity.id}</dd></div>
            </dl>
            <Collapsible defaultOpen={false}>
              <CollapsibleTrigger className="details-trigger">View raw JSON <ChevronDown aria-hidden="true" /></CollapsibleTrigger>
              <CollapsibleContent><pre>{JSON.stringify(presentation.raw, null, 2)}</pre></CollapsibleContent>
            </Collapsible>
          </CollapsibleContent>
        </Collapsible>
      </div>
    </article>
  )
}

function UnpresentedFactCard({ fact, candidateId }: { fact: Fact; candidateId: string }) {
  return (
    <article className="fact-row" id={sourceTarget(candidateId, "F", fact.fact_id)}>
      <div className="fact-copy">
        <div className="fact-heading">
          <h4>Presentation unavailable</h4>
          <span className="fact-id">{fact.fact_id}</span>
        </div>
        <p className="fact-observation">This canonical Fact is retained; its semantic summary could not be prepared.</p>
        <Collapsible className="source-details" defaultOpen={false}>
          <CollapsibleTrigger className="details-trigger">
            View technical source <ChevronDown aria-hidden="true" />
          </CollapsibleTrigger>
          <CollapsibleContent className="details-content">
            <dl className="source-metadata">
              <div><dt>Fact</dt><dd>{fact.fact_id}</dd></div>
              <div><dt>Source</dt><dd>{fact.source_ref}</dd></div>
              <div><dt>Source path</dt><dd>{fact.source_path}</dd></div>
              <div><dt>Entity</dt><dd>{fact.entity.type} / {fact.entity.id}</dd></div>
            </dl>
            <Collapsible defaultOpen={false}>
              <CollapsibleTrigger className="details-trigger">View raw JSON <ChevronDown aria-hidden="true" /></CollapsibleTrigger>
              <CollapsibleContent><pre>{JSON.stringify(fact, null, 2)}</pre></CollapsibleContent>
            </Collapsible>
          </CollapsibleContent>
        </Collapsible>
      </div>
    </article>
  )
}

function EvidenceSection({ facts, presentations, candidateId }: { facts: Fact[]; presentations: EvidencePresentation[]; candidateId: string }) {
  const byId = new Map(presentations.map((item) => [item.id, item]))
  const grouped = new Map<string, { entity: Fact["entity"]; facts: Fact[] }>()
  for (const fact of facts) {
    const key = `${fact.entity.type}:${fact.entity.id}`
    const group = grouped.get(key) ?? { entity: fact.entity, facts: [] }
    group.facts.push(fact)
    grouped.set(key, group)
  }
  const groups = [...grouped.values()]

  return (
    <section className="evidence-section" aria-labelledby="evidence-title">
      <div className="section-heading evidence-heading">
        <div className="section-symbol f-symbol">F</div>
        <div>
          <h2 id="evidence-title">Current evidence</h2>
          <p>Facts observed in this incident</p>
        </div>
        <span className="section-count">{facts.length} facts</span>
      </div>
      {facts.length === 0 ? (
        <p className="quiet-empty">No current incident facts are referenced by this candidate.</p>
      ) : (
        <div className="entity-groups">
          {groups.map(({ entity, facts: rows }) => (
            <div className="entity-group" key={`${entity.type}:${entity.id}`}>
              <div className="entity-header">
                <span className="entity-type">{entity.type}</span>
                <h3>{entity.id}</h3>
                <span className="entity-fact-count">{rows.length} {rows.length === 1 ? "fact" : "facts"}</span>
              </div>
              <div className="entity-facts">
                {rows.map((fact) => {
                  const presentation = byId.get(fact.fact_id)
                  return presentation
                    ? <FactCard fact={fact} presentation={presentation} candidateId={candidateId} key={fact.fact_id} />
                    : <UnpresentedFactCard fact={fact} candidateId={candidateId} key={fact.fact_id} />
                })}
              </div>
            </div>
          ))}
        </div>
      )}
    </section>
  )
}

function QualificationSection({ candidate, resolved }: { candidate: CandidateResult; resolved: ResolvedSources }) {
  if (candidate.qualifications.length === 0) {
    return null
  }
  return (
    <section className="qualification-section" aria-labelledby="qualification-title">
      <div className="section-heading">
        <div className="section-symbol q-symbol">!</div>
        <div>
          <h2 id="qualification-title">Validator qualification</h2>
          <p>The validator checks whether each claim is directly supported by available evidence. Unsupported parts remain visible as qualifications rather than being silently treated as facts.</p>
        </div>
      </div>
      <div className="qualification-list">
        {candidate.qualifications.map((qualification, index) => (
          <article className="qualification-row" key={`${qualification.claim}-${index}`}>
            <h3 className="qualification-number">Qualification {String(index + 1).padStart(2, "0")}</h3>
            <div className="qualification-pair">
              <div className="claim-block">
                <span>Proposed</span>
                <p>{qualification.claim}</p>
              </div>
              <div className="observed-block">
                <span>Observed</span>
                <p>{qualification.observed_form}</p>
              </div>
            </div>
            <div className="qualification-issue">
              <span>Validation issue</span>
              <p>{qualification.issue}</p>
              <small>Fact refs: {qualification.fact_refs.map((id) => <ReferenceChip key={id} id={id} kind="F" candidateId={candidate.hypothesis.id} exists={resolved.evidence.some((fact) => fact.fact_id === id)} />)}</small>
            </div>
          </article>
        ))}
      </div>
    </section>
  )
}

function UncertaintyGroup({ title, note, items }: { title: string; note: string; items: string[] }) {
  const [open, setOpen] = useState(false)
  const preview = items.slice(0, 1)
  return (
    <div className="uncertainty-column">
      <div className="uncertainty-heading">
        <h3>{title}</h3><span>{items.length}</span>
      </div>
      <p className="uncertainty-note">{note}</p>
      {items.length ? (
        <>
          <ul className={open ? "gap-list is-open" : "gap-list gap-preview"}>
            {(open ? items : preview).map((item, index) => <li key={`${title}-${index}`}><span className="gap-text">{item}</span></li>)}
          </ul>
          {items.length > 1 && (
            <button className="gap-toggle" type="button" onClick={() => setOpen(!open)}>
              {open ? "Show less" : `Show all ${items.length}`}
              <ChevronDown aria-hidden="true" />
            </button>
          )}
        </>
      ) : <p className="quiet-empty">None recorded.</p>}
    </div>
  )
}

function UncertaintySection({ candidate }: { candidate: CandidateResult }) {
  const questions = new Map<string, { text: string; sources: Set<string> }>()
  for (const [source, items] of [["Generator", candidate.hypothesis.unresolved], ["Validator", candidate.validation_unresolved]] as const) {
    for (const item of items) {
      const cleaned = item.trim().replace(/\s+/g, " ")
      const key = cleaned.toLocaleLowerCase()
      if (!key) continue
      const existing = questions.get(key) ?? { text: cleaned, sources: new Set<string>() }
      existing.sources.add(source)
      questions.set(key, existing)
    }
  }
  return (
    <section className="uncertainty-section" aria-label="Assumptions and unresolved questions">
      <div className="reasoning-gap-title"><h2>Open questions</h2></div>
      <div className="uncertainty-columns">
        <UncertaintyGroup title="Assumptions" note="Currently assumed by this explanation" items={candidate.hypothesis.assumptions} />
        <div className="uncertainty-column">
          <h3>What to inspect next</h3>
          {[...questions.values()].length ? <ul className="gap-list is-open">{[...questions.values()].map(({ text, sources }) => (
            <li key={text}><span className="open-question-text">{text}</span><small className="open-question-sources">{[...sources].join(" + ")}</small></li>
          ))}</ul> : <p className="quiet-empty">None recorded.</p>}
        </div>
      </div>
    </section>
  )
}

function HistorySection({ items, candidateId }: { items: ResolvedSources["history"]; candidateId: string }) {
  function historicalText(record: ResolvedSources["history"][number]["record"]) {
    const fields = [
      ["Past incident summary", record.incident_summary],
      ["Past incident cause", record.root_cause],
      ["Past incident summary", record.summary],
    ] as const
    return fields.find(([, value]) => typeof value === "string" && value.length > 0)
  }

  const groups = new Map<string, typeof items>()
  for (const item of items) {
    const summary = historicalText(item.record)
    const key = JSON.stringify([
      item.record.affected_component ?? null,
      summary?.[0] ?? null,
      summary?.[1] ?? null,
      typeof item.record.resolution === "string" ? item.record.resolution : null,
      typeof item.record.recommended_action === "string" ? item.record.recommended_action : null,
    ])
    groups.set(key, [...(groups.get(key) ?? []), item])
  }

  return (
    <section className="context-section history-context" aria-labelledby="history-title">
      <div className="section-heading compact-heading">
        <div className="section-symbol h-symbol">H</div>
        <div><h2 id="history-title">Historical precedent</h2><p>Seeded historical cases retrieved as context, not current evidence</p></div>
      </div>
      {items.length ? [...groups.values()].map((group) => {
        const item = group[0]
        const summary = historicalText(item.record)
        return (
        <article className="context-record historical-case" key={group.map((entry) => entry.alias).join("-")}>
          <div className="context-record-heading">
            <div className="context-identity">
              <strong>Historical case</strong>
              {item.record.affected_component && <span>{item.record.affected_component}</span>}
            </div>
            <div className="historical-aliases" aria-label="Historical source references">
              {group.map((entry) => <span key={entry.alias} id={sourceTarget(candidateId, "H", entry.alias)} className="historical-alias" title={`Source ${entry.source_id}${typeof entry.retrieval_rank === "number" ? ` · retrieval rank ${entry.retrieval_rank}` : ""}`}>{entry.alias}</span>)}
            </div>
          </div>
          <p className="historical-ranks">{group.map((entry) => typeof entry.retrieval_rank === "number" ? `${entry.alias} retrieved #${entry.retrieval_rank}` : null).filter(Boolean).join(" · ")}</p>
          <div className="context-summary-stack">
            {summary && (
              <div className="context-summary">
                <span>{summary[0]}</span>
                <p>{summary[1]}</p>
              </div>
            )}
            {typeof item.record.resolution === "string" && (
              <div className="context-summary"><span>Past resolution</span><p>{item.record.resolution}</p></div>
            )}
            {typeof item.record.recommended_action === "string" && (
              <div className="context-summary"><span>Past recommended action</span><p>{item.record.recommended_action}</p></div>
            )}
          </div>
          {group.map((entry) => (
            <Collapsible className="source-details" defaultOpen={false} key={`details-${entry.alias}`}>
              <CollapsibleTrigger className="details-trigger">View {entry.alias} source details <ChevronDown aria-hidden="true" /></CollapsibleTrigger>
              <CollapsibleContent className="details-content">
                <dl className="source-metadata"><div><dt>Source ID</dt><dd>{entry.source_id}</dd></div>{typeof entry.retrieval_rank === "number" && <div><dt>Retrieved rank</dt><dd>{entry.retrieval_rank}</dd></div>}{typeof entry.bm25_score === "number" && <div><dt>BM25 score</dt><dd>{entry.bm25_score}</dd></div>}</dl>
                <pre>{JSON.stringify(entry.record, null, 2)}</pre>
              </CollapsibleContent>
            </Collapsible>
          ))}
        </article>
      )}) : <p className="quiet-empty">No historical records referenced.</p>}
    </section>
  )
}

function KnowledgeSection({ items, candidateId }: { items: ResolvedSources["domain_knowledge"]; candidateId: string }) {
  return (
    <section className="context-section knowledge-context" aria-labelledby="knowledge-title">
      <div className="section-heading compact-heading">
        <div className="section-symbol k-symbol">K</div>
        <div><h2 id="knowledge-title">Domain context</h2><p>General sourced knowledge used to interpret the incident</p></div>
      </div>
      {items.length ? items.map((item) => {
        const source = item.record.source
        return (
        <article className="context-record" key={item.alias} id={sourceTarget(candidateId, "K", item.alias)}>
            <div className="context-record-heading">
              <div className="context-identity">
                <strong>{source?.title ?? item.record.knowledge_key ?? item.source_id}</strong>
                {source?.publisher && <span>{source.publisher}</span>}
              </div>
              {typeof item.retrieval_rank === "number" && <small>Retrieved #{item.retrieval_rank}</small>}
            </div>
            {item.record.claim && <p className="knowledge-claim">{item.record.claim}</p>}
            <div className="knowledge-provenance">
              {source?.section && <span>{source.section}</span>}
              {source?.url && <a href={source.url} target="_blank" rel="noreferrer">Open source</a>}
            </div>
            <Collapsible className="source-details" defaultOpen={false}>
              <CollapsibleTrigger className="details-trigger">View knowledge source details <ChevronDown aria-hidden="true" /></CollapsibleTrigger>
              <CollapsibleContent className="details-content">
                <dl className="source-metadata">
                  <div><dt>Knowledge key</dt><dd>{item.record.knowledge_key ?? "—"}</dd></div>
                  <div><dt>Source ID</dt><dd>{item.source_id}</dd></div>
                  {typeof item.retrieval_rank === "number" && <div><dt>Retrieved</dt><dd>{item.retrieval_rank}</dd></div>}
                  {typeof item.bm25_score === "number" && <div><dt>BM25 score</dt><dd>{item.bm25_score}</dd></div>}
                </dl>
                <pre>{JSON.stringify(item.record, null, 2)}</pre>
              </CollapsibleContent>
            </Collapsible>
          </article>
        )
      }) : <p className="quiet-empty">No domain knowledge referenced.</p>}
    </section>
  )
}

function CandidatePanel({ candidate, resolved }: { candidate: CandidateResult; resolved: ResolvedSources }) {
  return (
    <>
      <section className="explanation-panel" role="region" aria-labelledby="working-title">
        <div className="explanation-main">
          <span className="eyebrow">Working explanation</span>
          <h2 id="working-title">{candidate.hypothesis.explanation}</h2>
          <span className="candidate-id">Candidate ID · {candidate.hypothesis.id}</span>
        </div>
        <Separator orientation="vertical" className="explanation-divider" />
        <div className="assessment-stack">
          <div className={`support-result support-${candidate.analysis.support_level.toLowerCase()}`}>
            <span>Support</span>
            <strong>{supportLabels[candidate.analysis.support_level]}</strong>
          </div>
          <div className="validation-result">
            <span>Validation</span>
            <Badge variant="outline">{decisionLabel(candidate)}</Badge>
          </div>
        </div>
        <div className="candidate-refs" role="group" aria-label="Supporting sources">
        {candidate.evidence_refs.map((id) => <ReferenceChip key={`F-${id}`} id={id} kind="F" candidateId={candidate.hypothesis.id} exists={resolved.evidence.some((fact) => fact.fact_id === id)} />)}
        {candidate.history_refs.map((id) => <ReferenceChip key={`H-${id}`} id={id} kind="H" candidateId={candidate.hypothesis.id} exists={resolved.history.some((item) => item.alias === id)} />)}
        {candidate.knowledge_refs.map((id) => <ReferenceChip key={`K-${id}`} id={id} kind="K" candidateId={candidate.hypothesis.id} exists={resolved.domain_knowledge.some((item) => item.alias === id)} />)}
        </div>
      </section>
      <QualificationSection candidate={candidate} resolved={resolved} />
    </>
  )
}

function CandidateChooser({ result, selectedId, onChange }: {
  result: RCAResult
  selectedId: string
  onChange: (id: string) => void
}) {
  const candidates = result.candidate_results
  return (
    <section className="candidates" aria-label="Retained explanatory candidates">
      <div className="candidate-section-heading">
        <div>
          <h2>Retained explanations</h2>
          <p>{candidates.length} {candidates.length === 1 ? "candidate" : "candidates"}</p>
        </div>
        {candidates.length > 1 && <span className="order-note">Generator order · not ranked</span>}
      </div>
      {candidates.length === 0 ? (
        <div className="abstention-state">
          <div className="abstention-icon"><FileSearch aria-hidden="true" /></div>
          <div>
            <h3>No explanatory candidate was retained.</h3>
            <p>The current result contains no retained candidate.</p>
          </div>
        </div>
      ) : candidates.length === 1 ? (
        <div className="single-candidate-label">
          <CircleDot aria-hidden="true" /> Candidate {candidates[0].hypothesis.id}
        </div>
      ) : (
        <Tabs value={selectedId} onValueChange={onChange} className="candidate-tabs">
          <TabsList variant="line" className="candidate-tab-list">
            {candidates.map((candidate) => (
              <TabsTrigger className="candidate-tab" key={candidate.hypothesis.id} value={candidate.hypothesis.id}>
                <span>Candidate</span><strong>{candidate.hypothesis.id}</strong>
              </TabsTrigger>
            ))}
          </TabsList>
        </Tabs>
      )}
    </section>
  )
}

function Investigation({ incident, job, selectedId, onCandidateChange }: {
  incident: DemoIncident
  job: AnalysisJob
  selectedId: string
  onCandidateChange: (id: string) => void
}) {
  const result = job.result!
  const candidate = result.candidate_results.find((item) => item.hypothesis.id === selectedId)
  const resolved = candidate && job.resolved_sources_by_candidate?.[candidate.hypothesis.id]

  return (
    <section aria-label="RCA analysis result">
      <header className="incident-header">
        <div>
          <p className="breadcrumb">RCA <span>/</span> Investigation</p>
          <h1>{incident.title}</h1>
          <p className="incident-id">Incident <code>{result.incident_id}</code></p>
        </div>
        <div className="incident-summary">
          <span className="summary-label">Result</span>
          <strong>{result.candidate_results.length === 0 ? "No candidate retained" : `${result.candidate_results.length} retained`}</strong>
          <span>Prepared demo result</span>
        </div>
      </header>

      <CandidateChooser result={result} selectedId={selectedId} onChange={onCandidateChange} />

      {candidate && resolved ? (
        <>
          <CandidatePanel candidate={candidate} resolved={resolved} />
          <EvidenceSection facts={resolved.evidence} presentations={job.presented_facts ?? []} candidateId={candidate.hypothesis.id} />
          <div className="context-grid">
            <HistorySection items={resolved.history} candidateId={candidate.hypothesis.id} />
            <KnowledgeSection items={resolved.domain_knowledge} candidateId={candidate.hypothesis.id} />
          </div>
          <UncertaintySection candidate={candidate} />
        </>
      ) : (
        <div className="abstention-provenance">
          <div className="section-heading evidence-heading">
            <div className="section-symbol f-symbol">F</div>
            <div><h2>Current evidence</h2><p>Facts observed in this incident</p></div>
          </div>
          <p>No candidate-specific evidence, history, or domain context is attached to this empty result.</p>
        </div>
      )}
      <AnalysisExecution job={job} />
    </section>
  )
}

const signalLabels: Record<EvidenceSignal, string> = {
  metric: "Metrics", log: "Logs", trace: "Traces", kubernetes: "Kubernetes",
}

const scenarioOverviewCopy: Record<string, {
  context: string
  cause: string
  observations: string[]
  investigation: string[]
}> = {
  "missing-secret-01": {
    context: "A custom Kubernetes configuration exercise targets startup of the telemetry-docs workload.",
    cause: "A required environment-variable reference was added to the Deployment for a Secret verified absent from the namespace. Kubernetes could not create the new container configuration. The Secret value is not shown.",
    observations: [
      "A replacement telemetry-docs pod was Pending; its container was waiting with CreateContainerConfigError.",
      "A Kubernetes event reported that the referenced Secret was not found.",
      "A different telemetry-docs pod was Running and Ready in the same snapshot; these are separate pod observations, not a recovery sequence.",
    ],
    investigation: [
      "Relate the recorded Kubernetes event to the affected pod's startup state.",
      "Keep the separate Running pod as snapshot context, not as a transition.",
      "State what the Kubernetes-only evidence supports and what remains unobserved.",
    ],
  },
  "application-failure-01": {
    context: "The OpenTelemetry Demo Checkout and Payment services are examined after a prepared application-failure exercise.",
    cause: "The preparation script directs the operator to enable OpenTelemetry Demo's `paymentFailure` flag with a non-zero failure percentage. The flag generates errors for a selected share of Payment `charge` calls. The chosen percentage was not recorded.",
    observations: [
      "Payment-owned Charge traces recorded 6 errors (0 at baseline); mean duration rose from 2.18 ms to 14.33 ms.",
      "Checkout-owned PlaceOrder traces recorded 6 errors (0 at baseline), while mean duration fell from 310.78 ms to 269.86 ms.",
      "Checkout's client-side Charge traces recorded 6 errors; mean duration rose from 5.11 ms to 17.71 ms.",
      "Payment WARN logs appeared 6 times and include an `Invalid token` message; the log alone does not establish why the calls failed.",
    ],
    investigation: [
      "Assess how the Payment Charge errors relate to Checkout PlaceOrder errors.",
      "Compare service ownership, trace direction, latency changes, and the Payment warning without treating correlation as proof.",
      "Preserve the opposing PlaceOrder latency change and state unresolved causal details.",
    ],
  },
  "ad-high-cpu-01": {
    context: "The OpenTelemetry Demo Ad service is the focus of a prepared CPU-load exercise.",
    cause: "The preparation script directs the operator to enable OpenTelemetry Demo's `adHighCpu` flag before the incident window. The Demo documents this flag as triggering high CPU load in Ad. The capture does not preserve the exact flag state or variant.",
    observations: [
      "The Ad pod's CPU-usage metric rose sharply between baseline and incident windows; the source did not provide a concrete unit.",
      "Ad request logs show targeted and non-targeted product activity across the two windows.",
      "Ad GetAds traces recorded no errors in either window.",
      "The Ad pod was Running and Ready in the captured Kubernetes view.",
    ],
    investigation: [
      "Assess how the CPU increase relates to Ad request activity and the recorded trace behavior.",
      "Consider the Running/Ready pod state and error-free GetAds traces as counterevidence to service failure.",
      "Separate the documented CPU-load exercise from any unverified secondary cause.",
    ],
  },
  "dependency-unavailable-01": {
    context: "This OpenTelemetry Demo exercise examines checkout failures associated with requests from Checkout to Payment.",
    cause: "The pilot capture script asked the operator to enable OpenTelemetry Demo's `paymentUnreachable` feature flag for the incident window. The Demo documents this flag as making Checkout call Payment at an invalid address so Payment appears unavailable; the capture does not preserve the flag state itself.",
    observations: [
      "Checkout's outbound Payment Charge metric records incident responses labeled UNAVAILABLE; the parallel OK-labeled series is retained as contrasting context.",
      "Checkout-owned Charge and PlaceOrder traces record errors in the incident window, while their mean durations decrease rather than increase.",
      "The Payment-owned Charge trace summary has baseline samples but no incident samples, so Payment's internal handling is not directly observed.",
      "The captured Checkout pod is Running and Ready; this snapshot does not prove continuous health across the full window.",
    ],
    investigation: [
      "Determine how the outbound UNAVAILABLE status relates to Checkout's Charge and PlaceOrder errors.",
      "Keep client-side observations distinct from unobserved Payment server behavior.",
      "Assess the Running/Ready snapshot and decreasing latency without treating them as proof that no dependency failure occurred.",
    ],
  },
  "messaging-failure-01": {
    context: "This OpenTelemetry Demo exercise examines Checkout publishing and Fraud Detection consuming messages during a prepared queue/consumer stress simulation.",
    cause: "The pilot capture script asked the operator to enable OpenTelemetry Demo's `kafkaQueueProblems` feature flag. The captured logs record the queue-overload simulation and a Fraud Detection consumer delay; upstream documentation describes the flag as adding consumer-side delay. The capture does not independently establish that consumer lag increased.",
    observations: [
      "Checkout logs record the queue-overload simulation and its completion message; Fraud Detection logs record a one-second consumer delay.",
      "Fraud Detection's reported last-poll age rises from 0 to 18.5; the source does not specify a concrete unit.",
      "The measured consumer-lag metric stays at 0 in both windows, which limits a lag-spike conclusion.",
      "Checkout publish-orders trace mean latency rises from 19.414 ms to 88.732 ms, with no errors recorded in that operation summary.",
    ],
    investigation: [
      "Compare the recorded simulation with producer latency and Fraud Detection consumer observations.",
      "Treat the zero lag measurements as counterevidence and avoid assuming the broker or consumer stopped working.",
      "Separate the injected exercise from conclusions the captured signals cannot establish.",
    ],
  },
}

function ScenarioOverview({ incident, onAnalyze, busy }: {
  incident: DemoIncident
  onAnalyze: () => void
  busy: boolean
}) {
  const demoReady = incident.readiness === "demo-ready"
  const overviewCopy = scenarioOverviewCopy[incident.id]
  return (
    <section className="scenario-overview" aria-labelledby="overview-title">
      <div className="overview-heading">
        <div>
          <p className="breadcrumb">RCA <span>/</span> Prepared incident</p>
          <h1 id="overview-title">Scenario overview</h1>
          <div className="overview-title"><h2>{incident.title}</h2><Badge variant="secondary">{demoReady ? "Demo incident" : "Research scenario"}</Badge></div>
          <p className="overview-description">{demoReady ? overviewCopy?.context : "Captured for research; not yet validated for Demo v1."}</p>
        </div>
        <code className="overview-id">{incident.id}</code>
      </div>
      {demoReady && overviewCopy ? (
        <section className="scenario-cause" aria-labelledby="scenario-cause-title">
          <h3 id="scenario-cause-title">Known scenario cause</h3>
          <p>{overviewCopy.cause}</p>
        </section>
      ) : null}
      {demoReady && overviewCopy ? (
        <section className="incident-snapshot" aria-labelledby="observed-symptoms-title">
          <h3 id="observed-symptoms-title">Observed symptoms</h3>
          <ul>{overviewCopy.observations.map((observation) => <li key={observation}>{observation}</li>)}</ul>
        </section>
      ) : null}
      {demoReady ? <div className="overview-grid">
        <div className="overview-config">
          <h3>Incident configuration</h3>
          <dl>
            <div><dt>Affected services</dt><dd>{incident.affected_services?.join(", ")}</dd></div>
            <div><dt>Available telemetry</dt><dd>{incident.available_evidence_sources?.map((signal) => <Badge variant="outline" key={signal}>{signalLabels[signal]}</Badge>)}</dd></div>
            <div><dt>Analysis mode</dt><dd>{incident.analysis_mode}</dd></div>
          </dl>
        </div>
        <div className="overview-focus">
          <h3>What RCA will investigate</h3>
          <ul>{overviewCopy?.investigation.map((item) => <li key={item}>{item}</li>)}</ul>
        </div>
      </div> : null}
      {demoReady && <p className="rca-flow-note">RCA reviews current evidence, retrieves historical and domain context, proposes explanations, then checks claims against the observations. Unsupported parts may be qualified or rejected.</p>}
      <div className="overview-footer">
        <p>{demoReady ? "Telemetry is observation, not a confirmed root cause. RCA may return qualified hypotheses." : "This scenario is available to inspect, but cannot be analyzed in Demo v1."}</p>
        <Button className="analyze-button" onClick={onAnalyze} disabled={busy || !demoReady}>Analyze incident</Button>
      </div>
    </section>
  )
}

const sourceGroups = [
  { id: "otel-demo", title: "OpenTelemetry Demo" },
  { id: "custom-k8s", title: "Custom Kubernetes" },
] as const

function ScenarioLibrary({ incidents, selectedId, onSelect }: {
  incidents: DemoIncident[]
  selectedId: string
  onSelect: (id: string) => void
}) {
  const readyCount = incidents.filter((item) => item.readiness === "demo-ready").length
  return (
    <section className="scenario-library" aria-labelledby="scenario-library-title">
      <div className="library-heading">
        <div>
          <h1 id="scenario-library-title">Scenario Library</h1>
          <p>{incidents.length} collected incidents. {readyCount} are verified and runnable in RCA Demo v1.</p>
        </div>
      </div>
      <div className="library-groups">
        {sourceGroups.map((group) => (
          <section className="library-group" key={group.id} aria-labelledby={`group-${group.id}`}>
            <h2 id={`group-${group.id}`}>{group.title}</h2>
            <div className="scenario-rows">
              {incidents.filter((item) => item.source === group.id).map((item) => {
                const ready = item.readiness === "demo-ready"
                const status = ready ? "Demo v1 analysis available" : "Not yet available for Demo v1 analysis"
                return (
                  <button
                    className={`scenario-row${selectedId === item.id ? " is-selected" : ""}`}
                    key={item.id}
                    type="button"
                    aria-pressed={selectedId === item.id}
                    aria-label={`${item.title}. ${status}`}
                    onClick={() => onSelect(item.id)}
                  >
                    <span className="scenario-row-title">{item.title}</span>
                    <span className={`scenario-readiness${ready ? " is-ready" : " is-experimental"}`}>{status}</span>
                  </button>
                )
              })}
            </div>
          </section>
        ))}
      </div>
    </section>
  )
}

const stageLabels: Record<string, string> = {
  preparation: "Preparing incident",
  evidence: "Building and verifying evidence",
  retrieval: "Retrieving historical and domain context",
  generation: "Generating hypotheses",
  validation: "Validating hypotheses",
  assembly: "Assembling result",
}

const timingLabels: Record<string, string> = {
  preparation: "Incident preparation",
  evidence: "Evidence build and verification",
  retrieval: "Historical/domain retrieval",
  generation: "Generation local processing",
  validation: "Validation local processing",
  generation_provider: "Generation provider operation",
  validation_provider: "Validation provider operation",
  external_pacing: "External provider pacing",
  assembly: "Assembly",
}

function AnalysisProgress({ job, elapsed }: { job: AnalysisJob | null; elapsed: number }) {
  const stages = ["preparation", "evidence", "retrieval", "generation", "validation", "assembly"]
  const completed = new Set((job?.completed_stages ?? []).map((item) => item.stage))
  function stateFor(stage: string) {
    if (job?.stage === stage && job.status === "failed") return "failed"
    if (job?.stage === stage && job.status === "running") return "running"
    if (job?.status === "completed" || completed.has(stage)) return "completed"
    return "pending"
  }
  const stateText = { completed: "Completed", running: "Running", pending: "Pending", failed: "Failed" } as const
  const stateIcon = { completed: "✓", running: "→", pending: "•", failed: "!" } as const
  return <section className="analysis-progress" role="status" aria-label="Analysis progress">
    <strong>{job?.status === "queued" ? "Analysis queued" : job?.stage_label ?? "Analysis starting"}</strong>
    <ul>{stages.map((stage) => {
      const state = stateFor(stage)
      const item = [...(job?.completed_stages ?? [])].reverse().find((completedStage) => completedStage.stage === stage)
      const candidate = job?.stage === stage ? job.candidate_id : item?.candidate_id
      return <li key={stage} className={`progress-stage stage-${state}`}>
        <span className="stage-marker" aria-hidden="true">{stateIcon[state]}</span>
        <span>{stageLabels[stage]}</span>
        {candidate && <span className="progress-candidate">{candidate}</span>}
        <span className="stage-state">{stateText[state]}</span>
      </li>
    })}</ul>
    <span>Elapsed: {formatDuration(job?.elapsed_seconds ?? elapsed)}</span>
  </section>
}

function AnalysisExecution({ job }: { job: AnalysisJob }) {
  const audit = job.execution_audit
  if (!audit) return null
  return <section className="analysis-execution" aria-labelledby="execution-title">
    <h2 id="execution-title">Analysis execution</h2>
    <p>Measured wall-clock time. Provider operation includes provider-internal retry and backoff; external pacing is separate.</p>
    {audit.routing && <p className="execution-routing">
      Generator · {audit.routing.generator.provider} / {audit.routing.generator.model}; {" "}
      Validator · {audit.routing.validator.provider} / {audit.routing.validator.model}
    </p>}
    <dl>{audit.rows.map((row, index) => {
      const failedProviderStage = job.status === "failed" && job.stage && row.name === `${job.stage}_provider`
      const status = row.status === "partial" || failedProviderStage ? "failed" : job.status === "completed" ? "completed" : "pending"
      const stateLabel = status === "failed" ? "Failed" : status === "completed" ? "Completed" : "Pending"
      return <div key={`${row.name}-${row.candidate_id ?? index}`} className={`execution-row stage-${status}`}>
      <dt>{timingLabels[row.name] ?? row.name}{row.candidate_id ? ` · ${row.candidate_id}` : ""}<span className="stage-state">{stateLabel}</span></dt>
      <dd>{formatDuration(row.seconds)}</dd>
    </div>})}</dl>
    {audit.total_seconds !== null && <div className="execution-total"><strong>Total</strong><strong>{formatDuration(audit.total_seconds)}</strong></div>}
  </section>
}

export default function App() {
  const [incidents, setIncidents] = useState<DemoIncident[]>([])
  const [selectedIncidentId, setSelectedIncidentId] = useState("")
  const [catalogError, setCatalogError] = useState("")
  const [job, setJob] = useState<AnalysisJob | null>(null)
  const [phase, setPhase] = useState<"idle" | "submitting" | "polling" | "completed" | "error">("idle")
  const [error, setError] = useState("")
  const [elapsed, setElapsed] = useState(0)
  const [retryDelayRemaining, setRetryDelayRemaining] = useState(0)
  const [candidateOverride, setCandidateOverride] = useState("")
  const requestVersion = useRef(0)
  const startedAt = useRef(0)
  const incident = incidents.find((item) => item.id === selectedIncidentId)
  const busy = phase === "submitting" || phase === "polling"
  const currentCandidate = job?.result?.candidate_results.some((item) => item.hypothesis.id === candidateOverride)
    ? candidateOverride : job?.result?.candidate_results[0]?.hypothesis.id ?? ""

  useEffect(() => {
    let cancelled = false
    listIncidents().then((rows) => {
      if (!cancelled) {
        setIncidents(rows)
        setSelectedIncidentId(rows.find((row) => row.readiness === "demo-ready")?.id ?? "")
      }
    }).catch((failure: unknown) => {
      if (!cancelled) setCatalogError(failure instanceof Error ? failure.message : "Unable to load incidents")
    })
    return () => { cancelled = true; requestVersion.current += 1 }
  }, [])

  useEffect(() => {
    if (!busy) return
    const timer = window.setInterval(() => setElapsed(Math.floor((Date.now() - startedAt.current) / 1000)), 1000)
    return () => window.clearInterval(timer)
  }, [busy])

  useEffect(() => {
    if (phase !== "error" || retryDelayRemaining <= 0) return
    const timer = window.setTimeout(() => setRetryDelayRemaining((remaining) => Math.max(0, remaining - 1)), 1000)
    return () => window.clearTimeout(timer)
  }, [phase, retryDelayRemaining])

  function changeIncident(id: string) {
    requestVersion.current += 1
    setSelectedIncidentId(id)
    setJob(null)
    setPhase("idle")
    setError("")
    setRetryDelayRemaining(0)
    setElapsed(0)
    setCandidateOverride("")
  }

  async function analyzeSelectedIncident() {
    if (!incident || incident.readiness !== "demo-ready" || busy) return
    const version = ++requestVersion.current
    startedAt.current = Date.now()
    setElapsed(0)
    setError("")
    setRetryDelayRemaining(0)
    setJob(null)
    setPhase("submitting")
    try {
      const started = await startAnalysis(incident.id)
      if (version !== requestVersion.current) return
      setPhase("polling")
      setJob(started)
      for (;;) {
        const current = await getAnalysis(started.analysis_id)
        if (version !== requestVersion.current) return
        setJob(current)
        if (current.status === "completed") { setPhase("completed"); return }
        if (current.status === "failed") {
          setError(current.error?.code ?? "Analysis failed")
          setRetryDelayRemaining(current.error?.code === "RATE_LIMITED"
            ? Math.max(0, Math.ceil(current.error.retry_after_seconds ?? 0))
            : 0)
          setPhase("error")
          return
        }
        await new Promise((resolve) => window.setTimeout(resolve, 2000))
      }
    } catch (failure) {
      if (version !== requestVersion.current) return
      setError(failure instanceof Error ? failure.message : "Analysis failed")
      setPhase("error")
    }
  }

  return (
    <div className="app-shell">
      <header className="topbar">
        <a className="brand" href="#top" aria-label="RCA investigation home">
          <span className="brand-mark"><span /></span>
          <span><strong>RCA</strong><small>investigation</small></span>
        </a>
        <div className="demo-controls">
          <span className="demo-tag">Prepared demo</span>
          <span className="demo-tag">{incidents.length} scenarios · {incidents.filter((row) => row.readiness === "demo-ready").length} ready</span>
        </div>
      </header>
      <main className="page-main">
        {catalogError ? <div className="analysis-message" role="alert">Could not load demo incidents: {catalogError}</div> : null}
        {!catalogError && !incident ? <p className="analysis-message" role="status">Loading prepared incidents…</p> : null}
        {!catalogError && incidents.length > 0 && <ScenarioLibrary incidents={incidents} selectedId={selectedIncidentId} onSelect={changeIncident} />}
        {incident && <ScenarioOverview incident={incident} onAnalyze={analyzeSelectedIncident} busy={busy} />}
        {(busy || phase === "error") && job && <AnalysisProgress job={job} elapsed={elapsed} />}
        {phase === "error" && <>
          <div className="analysis-message error" role="alert">
            {job?.error?.code === "RATE_LIMITED"
              ? `The provider rate-limited this analysis. ${retryDelayRemaining > 0 ? `Wait ${formatDuration(retryDelayRemaining)} before retrying.` : "You can retry the analysis."} No RCA result was produced.`
              : `Analysis failed: ${error}. This is an execution failure, not an RCA abstention.`}
          </div>
          {job?.error?.code === "RATE_LIMITED" && <Button className="retry-analysis-button" onClick={analyzeSelectedIncident} disabled={busy || retryDelayRemaining > 0}>
            {retryDelayRemaining > 0 ? `Retry in ${formatDuration(retryDelayRemaining)}` : "Retry analysis"}
          </Button>}
          {job && <AnalysisExecution job={job} />}
        </>}
        {phase === "completed" && incident?.readiness === "demo-ready" && job?.result && (
          <Investigation incident={incident} job={job} selectedId={currentCandidate} onCandidateChange={setCandidateOverride} />
        )}
        {phase === "idle" && incident?.readiness === "demo-ready" && <p className="analysis-message">Review the incident above, then start an evidence-grounded analysis.</p>}
      </main>
      <footer className="page-footer">
        <span>RCA prepared demo</span><span>F current facts · H historical precedent · K domain context</span>
      </footer>
    </div>
  )
}
