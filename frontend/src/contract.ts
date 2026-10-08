export type Decision = "KEEP" | "KEEP_QUALIFIED" | "REJECT"
export type SupportLevel = "STRONG" | "PLAUSIBLE" | "WEAK" | "CONTRADICTED"

export interface Qualification {
  claim: string
  issue: string
  fact_refs: string[]
  observed_form: string
}

export interface CandidateResult {
  incident_id: string
  analysis: { decision: Decision; support_level: SupportLevel }
  hypothesis: {
    id: string
    explanation: string
    assumptions: string[]
    unresolved: string[]
  }
  evidence_refs: string[]
  history_refs: string[]
  knowledge_refs: string[]
  qualifications: Qualification[]
  validation_unresolved: string[]
}

export interface RCAResult {
  incident_id: string
  candidate_results: CandidateResult[]
}

export interface Fact {
  fact_id: string
  entity: { type: string; id: string }
  field: string
  value: unknown
  source_ref: string
  source_path: string
}

export interface EvidencePresentation {
  id: string
  signal_type: EvidenceSignal
  title: string
  statistic_kind: string | null
  baseline: number | null
  incident: number | null
  unit: string | null
  change: string | null
  source_service: string | null
  destination_service: string | null
  operation: string | null
  severity: string | null
  state: string | null
  preview: string | null
  technical: Record<string, unknown>
  raw: Fact
}

export interface IncidentSnapshotItem {
  observation_id: string
  source_ref: string
  presentation: EvidencePresentation
}

export interface HistoricalSource {
  alias: string
  source_id: string
  source_type: "HISTORY"
  retrieval_rank?: number
  bm25_score?: number
  record: {
    incident_id?: string
    affected_component?: string
    incident_summary?: string
    summary?: string
    root_cause?: string
    resolution?: string
    recommended_action?: string
    historical_evidence?: string
    resolution_note?: string
    [key: string]: unknown
  }
}

export interface KnowledgeSource {
  alias: string
  source_id: string
  source_type: "DOMAIN_KNOWLEDGE"
  retrieval_rank?: number
  bm25_score?: number
  record: {
    knowledge_key?: string
    claim?: string
    source?: { title?: string; publisher?: string; url?: string; section?: string }
    [key: string]: unknown
  }
}

export interface ResolvedSources {
  evidence: Fact[]
  history: HistoricalSource[]
  domain_knowledge: KnowledgeSource[]
}

export type EvidenceSignal = "metric" | "log" | "trace" | "kubernetes"

export interface DemoIncident {
  id: string
  title: string
  source: "otel-demo" | "custom-k8s"
  readiness: "demo-ready" | "experimental" | "unverified"
  prepared_input: string | null
  description?: string
  affected_services?: string[]
  symptoms?: string[]
  available_evidence_sources?: EvidenceSignal[]
  analysis_mode?: string
  investigation_focus?: string[]
  incident_snapshot?: IncidentSnapshotItem[]
}

export interface AnalysisJob {
  analysis_id: string
  incident_id: string
  status: "queued" | "running" | "completed" | "failed"
  stage?: string
  stage_label?: string
  candidate_id?: string | null
  started_at?: string
  stage_started_at?: string
  elapsed_seconds?: number
  completed_stages?: { stage: string; candidate_id?: string | null; seconds: number }[]
  execution_audit?: {
    total_seconds: number | null
    routing?: {
      generator: { provider: string; model: string }
      validator: { provider: string; model: string }
    } | null
    rows: { name: string; seconds: number; relationship: "exclusive" | "nested"; candidate_id?: string | null; status?: string }[]
  }
  result?: RCAResult
  facts?: Fact[]
  presented_facts?: EvidencePresentation[]
  fact_integrity?: boolean
  resolved_sources_by_candidate?: Record<string, ResolvedSources>
  error?: { code: string; retry_after_seconds?: number }
}
