"""In-process job manager: runs the pipeline in background executor tasks,
streams progress events to SSE subscribers, and maps LangGraph's human-review
interrupt() onto an async HTTP-decision handoff.

Design notes:
  - Single worker thread (ThreadPoolExecutor(max_workers=1)): one document
    actively PROCESSES at a time — the pipeline is CPU/RAM heavy (Docling +
    BGE-M3) and free LLM tiers are rate-limited, so serializing active runs is
    the correct local default. Additional uploads queue.
  - Waiting for a human review decision does NOT hold this worker slot. A
    paused run is durably checkpointed in Postgres (thread_id=document_id);
    the worker thread that hit the interrupt returns immediately. Submitting a
    review decision (POST /review) schedules a NEW executor task that resumes
    the SAME checkpoint. This matters: the previous design blocked the pool's
    one worker thread on `threading.Event.wait()` for up to 24h while paused —
    so a single un-reviewed document silently starved every other upload in
    the queue indefinitely, with no indication why. See pipeline/graph.py's
    run_document()/resume_document() split, which this builds on.
  - Jobs live in memory only while in flight; completed runs are persisted to
    Postgres by pipeline/persistence.py exactly like the CLI path. A restart
    loses queued/in-flight/awaiting-review job METADATA (status, event
    history — they'd need to be tracked again from the UI's perspective), but
    the underlying LangGraph checkpoint survives in Postgres untouched.
  - Event delivery: worker threads publish onto per-subscriber asyncio.Queues
    via loop.call_soon_threadsafe; each Job also keeps a full replayable
    `events` history so a subscriber that connects late (or reconnects) sees
    the whole timeline.
"""

from __future__ import annotations

import asyncio
import logging
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from pipeline.graph import RunOutcome

logger = logging.getLogger(__name__)

TERMINAL_STATUSES = {"completed", "rejected", "failed"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class Job:
    document_id: str
    filename: str
    pdf_path: str
    status: str = "queued"  # queued | processing | awaiting_review | completed | rejected | failed
    created_at: str = field(default_factory=_now)
    started_at: datetime | None = None  # set once, on first execution; preserved across a review pause/resume
    events: list[dict] = field(default_factory=list)
    review_payload: dict | None = None
    result_json: dict | None = None
    confidence: float | None = None
    decision: str | None = None
    run_id: str | None = None
    error: str | None = None

    def summary(self) -> dict:
        return {
            "id": self.document_id,
            "filename": self.filename,
            "status": self.status,
            "created_at": self.created_at,
            "confidence": self.confidence,
            "decision": self.decision,
            "run_id": self.run_id,
            "error": self.error,
            "source": "memory",
        }


class JobManager:
    def __init__(self) -> None:
        self._jobs: dict[str, Job] = {}
        self._lock = threading.Lock()
        self._subscribers: dict[str, list[asyncio.Queue]] = {}
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="pipeline")
        self._loop: asyncio.AbstractEventLoop | None = None

    # -- lifecycle ---------------------------------------------------------

    def bind_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        """Capture the server's event loop so worker threads can publish."""
        self._loop = loop

    # -- queries -----------------------------------------------------------

    def get(self, document_id: str) -> Job | None:
        with self._lock:
            return self._jobs.get(document_id)

    def all(self) -> list[Job]:
        with self._lock:
            return list(self._jobs.values())

    # -- submission --------------------------------------------------------

    def submit(self, document_id: str, filename: str, pdf_path: str) -> Job:
        job = Job(document_id=document_id, filename=filename, pdf_path=pdf_path)
        with self._lock:
            self._jobs[document_id] = job
        self._publish(job, {"type": "status", "status": "queued"})
        self._executor.submit(self._execute, job)
        return job

    def submit_review(self, document_id: str, decision: dict) -> bool:
        """Schedules a NEW executor task to resume a paused run from its
        checkpoint. Returns False if the job isn't currently awaiting review.
        Does not wait on or interact with any other job — resuming only has
        to wait for its turn in the (now-unblocked) single-worker queue."""
        job = self.get(document_id)
        if job is None or job.status != "awaiting_review":
            return False
        self._set_status(job, "processing", note="resuming after review")
        self._executor.submit(self._resume, job, decision)
        return True

    # -- SSE plumbing --------------------------------------------------------

    def subscribe(self, document_id: str) -> tuple[list[dict], asyncio.Queue]:
        """Returns (history snapshot, live queue). Caller must unsubscribe()."""
        queue: asyncio.Queue = asyncio.Queue()
        with self._lock:
            job = self._jobs.get(document_id)
            history = list(job.events) if job else []
            self._subscribers.setdefault(document_id, []).append(queue)
        return history, queue

    def unsubscribe(self, document_id: str, queue: asyncio.Queue) -> None:
        with self._lock:
            queues = self._subscribers.get(document_id, [])
            if queue in queues:
                queues.remove(queue)

    def _publish(self, job: Job, event: dict) -> None:
        event = {**event, "ts": _now()}
        with self._lock:
            job.events.append(event)
            queues = list(self._subscribers.get(job.document_id, []))
        if self._loop is not None:
            for q in queues:
                self._loop.call_soon_threadsafe(q.put_nowait, event)

    def _set_status(self, job: Job, status: str, **extra: Any) -> None:
        job.status = status
        self._publish(job, {"type": "status", "status": status, **extra})

    # -- the worker ----------------------------------------------------------

    def _execute(self, job: Job) -> None:
        # Heavy imports stay inside the worker so `uvicorn api.main:app` starts
        # instantly and a broken ML dep can't take the whole API down.
        from observability import traced_run_config
        from pipeline.graph import run_document
        from pipeline.pdf_safety import PdfSafetyError

        job.started_at = datetime.now(timezone.utc)
        self._set_status(job, "processing")

        def on_node(node_name: str) -> None:
            self._publish(job, {"type": "node", "node": node_name})

        try:
            run_config = traced_run_config(session_id=job.document_id, tags=["web"])
            outcome = run_document(job.document_id, job.pdf_path, run_config=run_config, on_node_update=on_node)
            self._handle_outcome(job, outcome)
        except PdfSafetyError as exc:
            job.error = "; ".join(exc.reasons)
            self._set_status(job, "rejected", reasons=exc.reasons)
        except Exception as exc:  # one bad document must never kill the worker
            logger.exception("Pipeline run failed for %s", job.document_id)
            job.error = f"{type(exc).__name__}: {exc}"
            self._set_status(job, "failed", error=job.error)

    def _resume(self, job: Job, decision: dict) -> None:
        # Runs in a FRESH executor task, possibly on a different worker
        # invocation than the one that originally paused — that's the whole
        # point (see module docstring). The checkpoint (keyed by
        # job.document_id) carries everything needed to continue.
        from observability import traced_run_config
        from pipeline.graph import resume_document

        def on_node(node_name: str) -> None:
            self._publish(job, {"type": "node", "node": node_name})

        try:
            run_config = traced_run_config(session_id=job.document_id, tags=["web"])
            outcome = resume_document(
                job.document_id, job.pdf_path, decision=decision, run_config=run_config, on_node_update=on_node
            )
            self._handle_outcome(job, outcome, human_review_decision=decision)
        except Exception as exc:
            logger.exception("Pipeline resume failed for %s", job.document_id)
            job.error = f"{type(exc).__name__}: {exc}"
            self._set_status(job, "failed", error=job.error)

    def _handle_outcome(self, job: Job, outcome: "RunOutcome", *, human_review_decision: dict | None = None) -> None:
        from pipeline.persistence import save_run

        if outcome.status == "paused":
            job.review_payload = outcome.interrupt_payload
            self._set_status(job, "awaiting_review", payload=outcome.interrupt_payload)
            return

        state = outcome.state
        job.result_json = state.result.model_dump(mode="json") if state.result else None
        job.confidence = state.result.confidence.score if state.result else None
        job.decision = state.result.review_decision.value if state.result else None
        job.run_id = save_run(
            state,
            started_at=job.started_at or datetime.now(timezone.utc),
            langfuse_session_id=job.document_id,
            human_review_decision=human_review_decision,
            source_filename=job.filename,
        )
        self._set_status(
            job,
            "completed",
            confidence=job.confidence,
            decision=job.decision,
            run_id=job.run_id,
        )


job_manager = JobManager()
