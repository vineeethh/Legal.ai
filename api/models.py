"""Request/response bodies for the HTTP API (separate from the internal Job record)."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from .jobs import Job, JobProgress, JobStatus


class HealthOut(BaseModel):
    status: Literal["ok"] = "ok"
    mode: Literal["demo", "live"]
    auth_required: bool
    version: str


class JobOut(BaseModel):
    """What clients see for a job — everything except the internal file path,
    the (large) result body and the review payload, which have their own endpoints."""

    id: str
    filename: str
    status: JobStatus
    demo: bool
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None
    progress: JobProgress
    error: str | None
    rejection_reasons: list[str]
    review_decision: dict[str, Any] | None
    has_result: bool
    confidence_score: float | None
    decision: str | None  # auto_save | needs_review | human_required
    processing_run_id: str | None

    @classmethod
    def from_job(cls, job: Job) -> "JobOut":
        confidence = (job.result or {}).get("confidence") or {}
        return cls(
            id=job.id,
            filename=job.filename,
            status=job.status,
            demo=job.demo,
            created_at=job.created_at,
            started_at=job.started_at,
            completed_at=job.completed_at,
            progress=job.progress,
            error=job.error,
            rejection_reasons=job.rejection_reasons,
            review_decision=job.review_decision,
            has_result=job.result is not None,
            confidence_score=confidence.get("score"),
            decision=(job.result or {}).get("review_decision"),
            processing_run_id=job.processing_run_id,
        )


class ReviewIn(BaseModel):
    action: Literal["approve", "reject", "edit"]
    # For "edit": top-level StructuredJudgment fields to replace, e.g.
    # {"metadata": {...}}. Same semantics as the CLI's JSON patch file.
    patches: dict[str, Any] | None = Field(default=None)


class EvalReportSummary(BaseModel):
    name: str
    created_at: str | None
    documents: int | None
    synthetic: bool
