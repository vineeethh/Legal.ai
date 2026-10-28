import type { JobStatus, ReviewDecision, VerificationStatus } from "./types";

export function pct(value: number | null | undefined, digits = 1): string {
  return value === null || value === undefined ? "—" : `${(value * 100).toFixed(digits)}%`;
}

export function relativeTime(iso: string | null): string {
  if (!iso) return "—";
  const seconds = Math.round((Date.now() - new Date(iso).getTime()) / 1000);
  if (seconds < 60) return "just now";
  if (seconds < 3600) return `${Math.floor(seconds / 60)} min ago`;
  if (seconds < 86400) return `${Math.floor(seconds / 3600)} h ago`;
  return new Date(iso).toLocaleDateString();
}

export function duration(start: string | null, end: string | null): string {
  if (!start) return "—";
  const ms = (end ? new Date(end).getTime() : Date.now()) - new Date(start).getTime();
  const s = Math.max(0, Math.round(ms / 1000));
  return s < 60 ? `${s}s` : `${Math.floor(s / 60)}m ${s % 60}s`;
}

export function formatDate(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(`${iso}T00:00:00`);
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" });
}

export const STATUS_LABEL: Record<JobStatus, string> = {
  queued: "Queued",
  running: "Processing",
  awaiting_review: "Needs your review",
  completed: "Completed",
  rejected: "Rejected (unsafe PDF)",
  failed: "Failed",
};

export const DECISION_LABEL: Record<ReviewDecision, string> = {
  auto_save: "Auto-saved",
  needs_review: "Saved · flagged for review",
  human_required: "Human review required",
};

export const VERIFICATION_LABEL: Record<VerificationStatus, string> = {
  verified: "Verified",
  mismatch: "Mismatch",
  not_found: "Not in KB",
  skipped: "Not checked",
};

export const ACT_LABEL: Record<string, string> = {
  indian_penal_code: "IPC 1860",
  code_of_criminal_procedure: "CrPC 1973",
  indian_evidence_act: "Evidence Act 1872",
  constitution_of_india: "Constitution",
  bharatiya_nyaya_sanhita: "BNS 2023",
  bharatiya_nagarik_suraksha_sanhita: "BNSS 2023",
  bharatiya_sakshya_adhiniyam: "BSA 2023",
  unknown: "Unknown act",
};

export const AGENT_LABEL: Record<string, string> = {
  metadata: "Metadata",
  facts: "Facts",
  statute: "Statutes",
  petitioner: "Petitioner",
  respondent: "Respondent",
  evidence: "Evidence",
};

export function humanize(field: string): string {
  return field.replace(/_/g, " ").replace(/^\w/, (c) => c.toUpperCase());
}
