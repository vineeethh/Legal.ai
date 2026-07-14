/** Friendly labels for pipeline graph nodes, in rough execution order. */
export const NODE_LABELS: Record<string, string> = {
  pdf_safety_gate: "Structural safety scan",
  parse_and_chunk: "Parse & chunk (Docling)",
  injection_screen: "Prompt-injection screen",
  rejected: "Rejected",
  metadata: "Metadata agent",
  metadata_confidence: "Metadata validation",
  facts: "Facts agent",
  facts_confidence: "Facts validation",
  statute: "Statute agent",
  statute_confidence: "Statute validation",
  petitioner: "Petitioner agent",
  petitioner_confidence: "Petitioner validation",
  respondent: "Respondent agent",
  respondent_confidence: "Respondent validation",
  evidence: "Evidence agent",
  evidence_confidence: "Evidence validation",
  fan_in_gate: "Sync barrier",
  assemble: "Statute verification (KB)",
  confidence: "Confidence scoring",
  human_review: "Human review",
};

export const STATUS_LABELS: Record<string, string> = {
  queued: "Queued",
  processing: "Processing",
  awaiting_review: "Awaiting review",
  completed: "Completed",
  rejected: "Rejected",
  failed: "Failed",
  unknown: "—",
};

export const DECISION_LABELS: Record<string, string> = {
  auto_save: "Auto-saved",
  needs_review: "Needs review",
  human_required: "Human required",
};

export const VERIFICATION_LABELS: Record<string, string> = {
  verified: "Verified",
  not_found: "Not found",
  mismatch: "Mismatch",
  skipped: "Skipped",
};

export const SIGNAL_LABELS: Record<string, { label: string; weight: number }> = {
  validation_pass_rate: { label: "Validation pass rate", weight: 0.35 },
  statute_verification_rate: { label: "Statute verification", weight: 0.2 },
  provenance_coverage: { label: "Provenance coverage", weight: 0.2 },
  schema_completeness: { label: "Schema completeness", weight: 0.15 },
  cross_agent_consistency: { label: "Cross-agent consistency", weight: 0.1 },
};

export function formatDate(iso: string | null | undefined): string {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleString(undefined, {
      day: "2-digit",
      month: "short",
      year: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return iso;
  }
}
