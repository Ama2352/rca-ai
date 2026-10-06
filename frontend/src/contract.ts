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
