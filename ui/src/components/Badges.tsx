import { DECISION_LABEL, STATUS_LABEL, VERIFICATION_LABEL } from "../format";
import type { JobStatus, ReviewDecision, VerificationStatus } from "../types";

const STATUS_TONE: Record<JobStatus, string> = {
  queued: "",
  running: "info",
  awaiting_review: "warn",
  completed: "ok",
  rejected: "bad",
  failed: "bad",
};

export function StatusBadge({ status }: { status: JobStatus }) {
  const live = status === "running" || status === "queued";
  return (
    <span className={`badge ${STATUS_TONE[status]}`}>
      <span className={`dot ${live ? "pulse" : ""}`} />
      {STATUS_LABEL[status]}
    </span>
  );
}

const DECISION_TONE: Record<ReviewDecision, string> = {
  auto_save: "ok",
  needs_review: "warn",
  human_required: "bad",
};

export function DecisionBadge({ decision }: { decision: ReviewDecision | null }) {
  if (!decision) return <span className="muted">—</span>;
  return <span className={`badge ${DECISION_TONE[decision]}`}>{DECISION_LABEL[decision]}</span>;
}

const VERIFICATION_TONE: Record<VerificationStatus, string> = {
  verified: "ok",
  mismatch: "bad",
  not_found: "warn",
  skipped: "",
};

export function VerificationBadge({ status }: { status: VerificationStatus }) {
  return <span className={`badge ${VERIFICATION_TONE[status]}`}>{VERIFICATION_LABEL[status]}</span>;
}

export function scoreTone(score: number | null | undefined): "ok" | "warn" | "bad" {
  if (score === null || score === undefined) return "warn";
  if (score >= 0.9) return "ok";
  if (score >= 0.8) return "warn";
  return "bad";
}
