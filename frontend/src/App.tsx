import { useState } from "react"
import {
  ArrowDownRight,
  ArrowUpRight,
  ChevronDown,
  CircleDot,
  FileSearch,
  Minus,
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
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { Separator } from "@/components/ui/separator"
import {
  Tabs,
  TabsList,
  TabsTrigger,
} from "@/components/ui/tabs"
import type { CandidateResult, Fact, SupportLevel } from "./contract"
import { scenarios } from "./mock/scenarios"
import type { DemoScenario } from "./mock/scenarios"

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

function humanize(value: string) {
  return value.replaceAll("_", " ").replace(/\b\w/g, (letter) => letter.toUpperCase())
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value)
}

function displayValue(value: unknown): string {
  if (typeof value === "string") return value
  if (typeof value === "number") return new Intl.NumberFormat("en", { maximumFractionDigits: 4 }).format(value)
  if (typeof value === "boolean") return value ? "true" : "false"
  if (value === null) return "null"
  return JSON.stringify(value)
}

function factChange(value: Record<string, unknown>) {
  const pairs = [
    ["baseline_median", "incident_median", "Median"],
    ["baseline_value", "incident_value", "Value"],
    ["baseline_count", "incident_count", "Count"],
    ["baseline_rate_per_min", "incident_rate_per_min", "Rate per minute"],
    ["baseline_mean_ms", "incident_mean_ms", "Mean"],
  ] as const
  return pairs.find(([before, after]) => before in value && after in value)
}

function ChangeMark({ change }: { change?: number }) {
  if (typeof change !== "number" || change === 0) return <Minus aria-hidden="true" />
  return change > 0 ? <ArrowUpRight aria-hidden="true" /> : <ArrowDownRight aria-hidden="true" />
}

function FactCard({ fact }: { fact: Fact }) {
  const value = fact.value
  const record = isRecord(value) ? value : undefined
  const change = record ? factChange(record) : undefined
  const signedChange = record && typeof record.signed_change === "number"
    ? record.signed_change
    : record && typeof record.signed_rate_change === "number"
      ? record.signed_rate_change
      : undefined
  const pattern = record && typeof record.pattern === "string" ? record.pattern : undefined
  const service = record && typeof record.service === "string" ? record.service : undefined
  const metric = record && typeof record.metric === "string" ? record.metric : undefined
  const operation = record && typeof record.operation_or_callee === "string"
    ? record.operation_or_callee
    : undefined
  const hasLatencyValues = record && [
    "baseline_mean_ms", "incident_mean_ms", "baseline_median_ms",
    "incident_median_ms", "signed_latency_change_ms",
  ].some((key) => key in record)
  const latencyIdentity = [service, operation].filter(Boolean).join(" / ")
  const factContext = hasLatencyValues ? "" : metric ? service ?? "" : [service, operation].filter(Boolean).join(" / ")
  const factTitle = pattern
    ? "Matched log pattern"
    : hasLatencyValues && latencyIdentity
      ? `${latencyIdentity} latency`
      : metric ?? humanize(fact.field)
  const detailFields = record
    ? Object.entries(record).filter(([key, detail]) => ![
      "baseline_median", "incident_median", "baseline_value", "incident_value",
      "baseline_count", "incident_count", "baseline_rate_per_min", "incident_rate_per_min",
      "baseline_mean_ms", "incident_mean_ms", "signed_change", "signed_rate_change",
    ].includes(key) && !isRecord(detail) && !Array.isArray(detail))
    : []

  return (
    <article className="fact-row">
      <div className="fact-copy">
        <div className="fact-heading">
          <h4>{factTitle}</h4>
          <span className="fact-id">{fact.fact_id}</span>
        </div>
        {factContext && <p className="fact-context">{factContext}</p>}
        {change && record ? (
          <div className="change-line">
            <div className="change-values">
              <span>{displayValue(record[change[0]])}</span>
              <span className="change-arrow" aria-label="to">→</span>
              <strong>{displayValue(record[change[1]])}</strong>
            </div>
            <div className="change-caption">
              <ChangeMark change={signedChange} />
              <span>{change[2]} · baseline to incident</span>
              {typeof signedChange === "number" && (
                <span className="signed-change">{signedChange > 0 ? "+" : ""}{displayValue(signedChange)}</span>
              )}
            </div>
          </div>
        ) : pattern ? (
          <p className="fact-observation">{pattern}</p>
        ) : !record && !Array.isArray(value) ? (
          <p className="fact-observation">{displayValue(value)}</p>
        ) : Array.isArray(value) ? (
          <ul className="fact-observation-list">
            {value.map((item, index) => <li key={index}>{displayValue(item)}</li>)}
          </ul>
        ) : null}
        {detailFields.length > 0 && record && (
          <dl className="fact-attributes">
            {detailFields.slice(0, 3).map(([key, detail]) => (
              <div key={key}>
                <dt>{humanize(key)}</dt>
                <dd>{displayValue(detail)}</dd>
              </div>
            ))}
          </dl>
        )}
        <Collapsible className="source-details" defaultOpen={false}>
          <CollapsibleTrigger className="details-trigger">
            View source details <ChevronDown aria-hidden="true" />
          </CollapsibleTrigger>
          <CollapsibleContent className="details-content">
            <dl className="source-metadata">
              <div><dt>Fact</dt><dd>{fact.fact_id}</dd></div>
              <div><dt>Source</dt><dd>{fact.source_ref}</dd></div>
              <div><dt>Source path</dt><dd>{fact.source_path}</dd></div>
              <div><dt>Entity</dt><dd>{fact.entity.type} / {fact.entity.id}</dd></div>
            </dl>
            <pre>{JSON.stringify({ field: fact.field, value: fact.value }, null, 2)}</pre>
          </CollapsibleContent>
        </Collapsible>
      </div>
    </article>
  )
}

function EvidenceSection({ facts }: { facts: Fact[] }) {
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
                {rows.map((fact) => <FactCard fact={fact} key={fact.fact_id} />)}
              </div>
            </div>
          ))}
        </div>
      )}
    </section>
  )
}

function QualificationSection({ candidate }: { candidate: CandidateResult }) {
  if (candidate.analysis.decision !== "KEEP_QUALIFIED" || candidate.qualifications.length === 0) {
    return null
  }
  return (
    <section className="qualification-section" aria-labelledby="qualification-title">
      <div className="section-heading">
        <div className="section-symbol q-symbol">!</div>
        <div>
          <h2 id="qualification-title">Validator qualification</h2>
          <p>The retained wording extends beyond what the linked facts directly show.</p>
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
              <small>Fact refs: {qualification.fact_refs.join(", ")}</small>
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
            {(open ? items : preview).map((item, index) => <li key={`${title}-${index}`}>{item}</li>)}
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
  const groups = [
    { title: "Assumptions", note: "Currently assumed by this explanation", items: candidate.hypothesis.assumptions },
    { title: "Hypothesis unresolved", note: "Gaps named by the Generator", items: candidate.hypothesis.unresolved },
    { title: "Validation unresolved", note: "Gaps retained by the Validator", items: candidate.validation_unresolved },
  ]
  return (
    <section className="uncertainty-section" aria-label="Assumptions and unresolved questions">
      <div className="reasoning-gap-title"><h2>Reasoning gaps</h2></div>
      <div className="uncertainty-columns">
        {groups.map((group) => <UncertaintyGroup {...group} key={group.title} />)}
      </div>
    </section>
  )
}

function HistorySection({ items }: { items: NonNullable<DemoScenario["resolvedSources"][number]["history"]> }) {
  function historicalText(record: DemoScenario["resolvedSources"][number]["history"][number]["record"]) {
    const fields = [
      ["Past incident summary", record.incident_summary],
      ["Past incident cause", record.root_cause],
      ["Past incident summary", record.summary],
    ] as const
    return fields.find(([, value]) => typeof value === "string" && value.length > 0)
  }

  return (
    <section className="context-section history-context" aria-labelledby="history-title">
      <div className="section-heading compact-heading">
        <div className="section-symbol h-symbol">H</div>
        <div><h2 id="history-title">Historical precedent</h2><p>Prior incidents retrieved as context, not current evidence</p></div>
      </div>
      {items.length ? items.map((item) => {
        const summary = historicalText(item.record)
        return (
        <article className="context-record" key={item.alias}>
          <div className="context-record-heading">
            <div className="context-identity">
              <strong>{item.record.incident_id ?? item.source_id}</strong>
              {item.record.affected_component && <span>{item.record.affected_component}</span>}
            </div>
            {typeof item.retrieval_rank === "number" && <small>Retrieved #{item.retrieval_rank}</small>}
          </div>
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
          <Collapsible className="source-details" defaultOpen={false}>
            <CollapsibleTrigger className="details-trigger">View historical details <ChevronDown aria-hidden="true" /></CollapsibleTrigger>
            <CollapsibleContent className="details-content">
              <pre>{JSON.stringify(item.record, null, 2)}</pre>
            </CollapsibleContent>
          </Collapsible>
        </article>
      )}) : <p className="quiet-empty">No historical records referenced.</p>}
    </section>
  )
}

function KnowledgeSection({ items }: { items: NonNullable<DemoScenario["resolvedSources"][number]["domain_knowledge"]> }) {
  return (
    <section className="context-section knowledge-context" aria-labelledby="knowledge-title">
      <div className="section-heading compact-heading">
        <div className="section-symbol k-symbol">K</div>
        <div><h2 id="knowledge-title">Domain context</h2><p>General sourced knowledge used to interpret the incident</p></div>
      </div>
      {items.length ? items.map((item) => {
        const source = item.record.source
        return (
          <article className="context-record" key={item.alias}>
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

function CandidatePanel({ candidate }: { candidate: CandidateResult }) {
  return (
    <>
      <section className="explanation-panel" aria-labelledby="working-title">
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
      </section>
      <QualificationSection candidate={candidate} />
      <UncertaintySection candidate={candidate} />
    </>
  )
}

function CandidateChooser({ scenario, selectedId, onChange }: {
  scenario: DemoScenario
  selectedId: string
  onChange: (id: string) => void
}) {
  const candidates = scenario.result.candidate_results
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

function Investigation({ scenario, selectedId, onCandidateChange }: {
  scenario: DemoScenario
  selectedId: string
  onCandidateChange: (id: string) => void
}) {
  const candidateIndex = scenario.result.candidate_results.findIndex((candidate) => candidate.hypothesis.id === selectedId)
  const candidate = scenario.result.candidate_results[candidateIndex]
  const resolved = scenario.resolvedSources[candidateIndex]

  return (
    <main className="page-main">
      <header className="incident-header">
        <div>
          <p className="breadcrumb">RCA <span>/</span> Investigation</p>
          <h1>{scenario.label.replace(/ · .*$/, "")}</h1>
          <p className="incident-id">Incident <code>{scenario.result.incident_id}</code></p>
        </div>
        <div className="incident-summary">
          <span className="summary-label">Result</span>
          <strong>{scenario.result.candidate_results.length === 0 ? "No candidate retained" : `${scenario.result.candidate_results.length} retained`}</strong>
          <span>Prepared demo result</span>
        </div>
      </header>

      {scenario.preview && (
        <p className="preview-note">
          {scenario.id === "abstention"
            ? "Contract-state preview · empty candidate_results list"
            : "Candidate-count preview · derived from saved Missing Secret candidates in Generator order"}
        </p>
      )}
      <CandidateChooser scenario={scenario} selectedId={selectedId} onChange={onCandidateChange} />

      {candidate && resolved ? (
        <>
          <CandidatePanel candidate={candidate} />
          <EvidenceSection facts={resolved.evidence} />
          <div className="context-grid">
            <HistorySection items={resolved.history} />
            <KnowledgeSection items={resolved.domain_knowledge} />
          </div>
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
    </main>
  )
}

export default function App() {
  const [pendingScenarioId, setPendingScenarioId] = useState("missing-secret")
  const [activeScenarioId, setActiveScenarioId] = useState("missing-secret")
  const scenario = scenarios.find((item) => item.id === activeScenarioId) ?? scenarios[0]
  const selectedCandidateId = scenario.result.candidate_results[0]?.hypothesis.id ?? ""
  const [candidateOverride, setCandidateOverride] = useState("")
  const currentCandidate = scenario.result.candidate_results.some((item) => item.hypothesis.id === candidateOverride)
    ? candidateOverride
    : selectedCandidateId

  function analyzeSelectedScenario() {
    setActiveScenarioId(pendingScenarioId)
    setCandidateOverride("")
  }

  return (
    <div className="app-shell">
      <header className="topbar">
        <a className="brand" href="#top" aria-label="RCA investigation home">
          <span className="brand-mark"><span /></span>
          <span><strong>RCA</strong><small>investigation</small></span>
        </a>
        <div className="demo-controls">
          <span className="demo-tag">Mock data</span>
          <Select value={pendingScenarioId} onValueChange={(value) => value && setPendingScenarioId(value)}>
            <SelectTrigger aria-label="Choose demo scenario" className="scenario-select">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {scenarios.map((item) => (
                <SelectItem key={item.id} value={item.id}>{item.label}</SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Button className="analyze-button" onClick={analyzeSelectedScenario}>Analyze incident</Button>
        </div>
      </header>
      <Investigation
        scenario={scenario}
        selectedId={currentCandidate}
        onCandidateChange={setCandidateOverride}
      />
      <footer className="page-footer">
        <span>RCA public result draft</span><span>F current facts · H historical precedent · K domain context</span>
      </footer>
    </div>
  )
}
