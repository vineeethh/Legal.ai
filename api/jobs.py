"""Job records for API runs + a thread-safe store that mirrors each job to disk.

One job = one uploaded PDF going through the pipeline. Jobs live in memory and
are also written to `<jobs_dir>/<id>.json` after every change, so finished
results survive an API restart. A job that was still running (or waiting for
review) when the process stopped cannot be resumed — its chunks and embedding
index lived only in that process — so it is marked failed on the next start.
"""

from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Callable

from pydantic import BaseModel, Field

from schemas import AgentName

EXTRACTION_AGENTS = [a.value for a in AgentName if a != AgentName.RESPONSE]


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class JobStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    AWAITING_REVIEW = "awaiting_review"
    COMPLETED = "completed"
    REJECTED = "rejected"  # failed the PDF safety scan
    FAILED = "failed"


TERMINAL_STATUSES = {JobStatus.COMPLETED, JobStatus.REJECTED, JobStatus.FAILED}


class AgentProgress(BaseModel):
    # pending -> running -> validating -> (retrying -> running ...) -> done
    status: str = "pending"
    attempts: int = 0


class JobProgress(BaseModel):
    current_node: str | None = None
    completed_nodes: list[str] = Field(default_factory=list)
    agents: dict[str, AgentProgress] = Field(
        default_factory=lambda: {name: AgentProgress() for name in EXTRACTION_AGENTS}
    )


class Job(BaseModel):
    id: str
    filename: str
    pdf_path: str
    status: JobStatus = JobStatus.QUEUED
    demo: bool = False

    created_at: datetime = Field(default_factory=utcnow)
    started_at: datetime | None = None
    completed_at: datetime | None = None

    progress: JobProgress = Field(default_factory=JobProgress)
    error: str | None = None
    rejection_reasons: list[str] = Field(default_factory=list)

    # Set while status == awaiting_review: the human_review interrupt payload.
    review_payload: dict[str, Any] | None = None
    # The reviewer's decision, once given ({"action": ..., "patches": ...}).
    review_decision: dict[str, Any] | None = None

    result: dict[str, Any] | None = None  # StructuredJudgment as JSON
    processing_run_id: str | None = None  # processing_runs.id when saved to Postgres


class JobStore:
    def __init__(self, jobs_dir: Path):
        self._dir = jobs_dir
        self._dir.mkdir(parents=True, exist_ok=True)
        self._jobs: dict[str, Job] = {}
        self._lock = threading.Lock()

    def load(self) -> None:
        """Reads persisted jobs; anything not finished is marked failed."""
        for path in sorted(self._dir.glob("*.json")):
            try:
                job = Job.model_validate_json(path.read_text())
            except ValueError:
                continue
            if job.status not in TERMINAL_STATUSES:
                job.status = JobStatus.FAILED
                job.error = "The API restarted before this run finished. Upload the PDF again."
                job.review_payload = None
                job.completed_at = utcnow()
                self._write(job)
            self._jobs[job.id] = job

    def add(self, job: Job) -> Job:
        with self._lock:
            self._jobs[job.id] = job
            self._write(job)
            return job.model_copy(deep=True)

    def get(self, job_id: str) -> Job | None:
        with self._lock:
            job = self._jobs.get(job_id)
            return job.model_copy(deep=True) if job else None

    def list(self) -> list[Job]:
        with self._lock:
            jobs = [j.model_copy(deep=True) for j in self._jobs.values()]
        return sorted(jobs, key=lambda j: j.created_at, reverse=True)

    def update(self, job_id: str, mutate: Callable[[Job], None]) -> Job:
        """Applies `mutate` to the stored job under the lock, then persists it."""
        with self._lock:
            job = self._jobs[job_id]
            mutate(job)
            self._write(job)
            return job.model_copy(deep=True)

    def _write(self, job: Job) -> None:
        self._dir.mkdir(parents=True, exist_ok=True)
        tmp = self._dir / f"{job.id}.json.tmp"
        tmp.write_text(json.dumps(job.model_dump(mode="json"), indent=2))
        tmp.replace(self._dir / f"{job.id}.json")
