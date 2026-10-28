// Mirrors the Pydantic models in schemas/ (as JSON) and api/models.py.

export interface SourceRef {
  page: number;
  quote: string;
  char_start?: number | null;
  char_end?: number | null;
  chunk_id?: string | null;
  section_path?: string | null;
}

export interface Sourced<T> {
  value: T | null;
  sources: SourceRef[];
  extraction_confidence?: number | null;
}

export interface SourcedItem<T> {
  value: T;
  sources: SourceRef[];
  extraction_confidence?: number | null;
}

export interface Party {
  name: string;
  role?: string | null;
}

export interface MetadataOutput {
  court: Sourced<string>;
  bench: Sourced<string>;
  judges: SourcedItem<string>[];
  decision_date: Sourced<string>;
  case_number: Sourced<string>;
  petitioners: SourcedItem<Party>[];
  respondents: SourcedItem<Party>[];
  jurisdiction: Sourced<string>;
}

export interface TimelineEvent {
  event_date?: string | null;
  description: string;
}

export interface FactsOutput {
  background: Sourced<string>;
  incident_summary: Sourced<string>;
  key_facts: SourcedItem<string>[];
  timeline: SourcedItem<TimelineEvent>[];
}

export type VerificationStatus = "verified" | "not_found" | "mismatch" | "skipped";

export interface KBMatch {
  act: string;
  act_version: string;
  section_number: string;
  section_title?: string | null;
  official_text: string;
  similarity_score: number;
}

export interface StatuteReference {
  raw_citation: string;
  parsed_act: string;
  parsed_section?: string | null;
  sources: SourceRef[];
  verification_status: VerificationStatus;
  kb_match?: KBMatch | null;
  verification_note?: string | null;
  current_equivalent?: KBMatch | null;
}

export interface Argument {
  summary: string;
  relied_on?: string | null;
}

export interface ArgumentsOutput {
  party_side: string;
  arguments: SourcedItem<Argument>[];
}

export type EvidenceKind = "witness" | "document" | "physical" | "digital";

export interface EvidenceItem {
  kind: EvidenceKind;
  description: string;
  label?: string | null;
}

export type ReviewDecision = "auto_save" | "needs_review" | "human_required";

export interface ConfidenceBreakdown {
  validation_pass_rate: number;
  statute_verification_rate: number;
  provenance_coverage: number;
  schema_completeness: number;
  cross_agent_consistency: number;
  score: number;
  decision: ReviewDecision;
}

export interface StructuredJudgment {
  metadata: MetadataOutput;
  facts: FactsOutput;
  statutes: { references: StatuteReference[] };
  petitioner: ArgumentsOutput;
  respondent: ArgumentsOutput;
  evidence: { items: SourcedItem<EvidenceItem>[] };
  confidence: ConfidenceBreakdown;
  review_decision: ReviewDecision;
  processing: {
    document_id: string;
    schema_version: string;
    llm_model: string;
    prompt_versions: Record<string, string>;
    retry_counts: Record<string, number>;
    processed_at: string;
  };
}

export type JobStatus = "queued" | "running" | "awaiting_review" | "completed" | "rejected" | "failed";

export interface AgentProgress {
  status: "pending" | "running" | "validating" | "retrying" | "done";
  attempts: number;
}

export interface Job {
  id: string;
  filename: string;
  status: JobStatus;
  demo: boolean;
  created_at: string;
  started_at: string | null;
  completed_at: string | null;
  progress: {
    current_node: string | null;
    completed_nodes: string[];
    agents: Record<string, AgentProgress>;
  };
  error: string | null;
  rejection_reasons: string[];
  review_decision: ReviewAction | null;
  has_result: boolean;
  confidence_score: number | null;
  decision: ReviewDecision | null;
  processing_run_id: string | null;
}

export interface ReviewAction {
  action: "approve" | "reject" | "edit";
  patches?: Record<string, unknown> | null;
}

export interface FlaggedField {
  agent: string;
  field_path: string;
  status: string;
  reason: string | null;
}

export interface ReviewPayload {
  document_id: string;
  decision: ReviewDecision;
  confidence_score: number;
  flagged_fields: FlaggedField[];
  result_preview: StructuredJudgment;
}

export interface Health {
  status: "ok";
  mode: "demo" | "live";
  auth_required: boolean;
  version: string;
}

// ---- evaluation reports (evaluation/run_eval.py) ----

export interface OutcomeSummary {
  n: number;
  counts: Record<string, number>;
  accuracy: number | null;
  error_rate_when_answered: number | null;
  abstention_rate: number | null;
}

export interface ListScore {
  tp: number;
  fp: number;
  fn: number;
  precision: number | null;
  recall: number | null;
  f1: number | null;
}

export interface EvalReport {
  run: {
    created_at: string;
    documents_labelled: number;
    documents_scored: number;
    missing_predictions: string[];
    llm_models: string[];
    synthetic: boolean;
  };
  summary: {
    scalar_overall: OutcomeSummary;
    scalar_fields: Record<string, OutcomeSummary>;
    list_fields: Record<string, ListScore>;
    statutes: { extraction: ListScore | null; verification_status_counts: Record<string, number> };
    calibration: {
      pearson_confidence_vs_doc_score: number | null;
      by_review_decision: Record<string, { documents: number; mean_doc_score: number }>;
    };
    provenance: { sourced_values: number; with_chunk_id: number; rate: number | null };
  };
  documents: {
    case_id: string;
    confidence_score: number;
    review_decision: ReviewDecision;
    scalar_accuracy: number | null;
    doc_score: number | null;
  }[];
}

export interface EvalReportSummary {
  name: string;
  created_at: string | null;
  documents: number | null;
  synthetic: boolean;
}
