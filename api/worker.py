"""Runs jobs in background threads and bridges human review across HTTP requests.

Why threads and not a separate task queue: the pipeline's human-review step is
a callback (`on_human_review`) that must *return* the reviewer's decision, and
the run's chunks + embedding index live only in that call's memory (they are
not checkpointed, see RunContext in pipeline/graph.py). Keeping the run alive
in a thread that waits on an Event lets `POST /review` hand the decision
straight to the paused graph, with no change to the pipeline itself.

Trade-off: a run paused for review does not survive an API restart.
"""

from __future__ import annotations

import logging
import threading
import traceback
from typing import Any

from .jobs import Job, JobStatus, JobStore, utcnow
from .pipelines import DocumentRejected, Pipeline

logger = logging.getLogger(__name__)


class _ReviewWaiter:
    def __init__(self) -> None:
        self.event = threading.Event()
        self.decision: dict | None = None


def _key(value: Any) -> str:
    """AgentName enum keys (real pipeline) and plain strings (demo) -> 'facts' etc."""
    return getattr(value, "value", value)


def apply_progress(job: Job, node: str, update: dict) -> None:
    """Folds one finished graph node into the job's progress view."""
    progress = job.progress
    progress.current_node = node
    progress.completed_nodes.append(node)

    if node in progress.agents:  # an extraction attempt just finished
        agent = progress.agents[node]
        agent.attempts += 1
        agent.status = "validating"
        return

    if node.endswith("_confidence"):
        agent_name = node.removesuffix("_confidence")
        agent = progress.agents.get(agent_name)
        if agent is None:
            return
        decisions = {_key(k): v for k, v in (update.get("retry_decision") or {}).items()}
        agent.status = "retrying" if decisions.get(agent_name) == "retry" else "done"
        return

    if node == "injection_screen":
        for agent in progress.agents.values():
            agent.status = "running"


class JobRunner:
    def __init__(self, store: JobStore, pipeline: Pipeline, *, max_concurrent_jobs: int):
        self._store = store
        self._pipeline = pipeline
        self._slots = threading.Semaphore(max(1, max_concurrent_jobs))
        self._waiters: dict[str, _ReviewWaiter] = {}
        self._waiters_lock = threading.Lock()

    def submit(self, job_id: str) -> None:
        threading.Thread(target=self._run, args=(job_id,), name=f"job-{job_id[:8]}", daemon=True).start()

    def submit_review(self, job_id: str, decision: dict) -> bool:
        """Hands a reviewer's decision to the paused run. False if it isn't waiting."""
        with self._waiters_lock:
            waiter = self._waiters.pop(job_id, None)
        if waiter is None:
            return False
        waiter.decision = decision
        waiter.event.set()
        return True

    def _run(self, job_id: str) -> None:
        self._slots.acquire()
        holding_slot = True

        def on_progress(node: str, update: dict) -> None:
            self._store.update(job_id, lambda job: apply_progress(job, node, update))

        def on_review(payload: dict) -> dict:
            nonlocal holding_slot
            waiter = _ReviewWaiter()
            # Register before flipping the status, so a review that arrives
            # the moment the UI sees "awaiting_review" always finds the waiter.
            with self._waiters_lock:
                self._waiters[job_id] = waiter

            def mark_waiting(job: Job) -> None:
                job.status = JobStatus.AWAITING_REVIEW
                job.review_payload = payload

            self._store.update(job_id, mark_waiting)
            # A run waiting on a person shouldn't block other uploads.
            self._slots.release()
            holding_slot = False
            waiter.event.wait()
            self._slots.acquire()
            holding_slot = True

            def mark_resumed(job: Job) -> None:
                job.status = JobStatus.RUNNING
                job.review_payload = None
                job.review_decision = waiter.decision

            self._store.update(job_id, mark_resumed)
            return waiter.decision or {"action": "approve"}

        try:
            def mark_running(job: Job) -> None:
                job.status = JobStatus.RUNNING
                job.started_at = utcnow()

            job = self._store.update(job_id, mark_running)
            outcome = self._pipeline.run(job, on_progress, on_review)

            def mark_completed(job: Job) -> None:
                job.status = JobStatus.COMPLETED
                job.result = outcome.result
                job.review_decision = outcome.human_review_decision
                job.processing_run_id = outcome.processing_run_id
                job.progress.current_node = None
                job.completed_at = utcnow()

            self._store.update(job_id, mark_completed)
        except DocumentRejected as exc:
            reasons = exc.reasons

            def mark_rejected(job: Job) -> None:
                job.status = JobStatus.REJECTED
                job.rejection_reasons = reasons
                job.progress.current_node = None
                job.completed_at = utcnow()

            self._store.update(job_id, mark_rejected)
        except Exception as exc:  # surfaced to the client as status=failed
            logger.error("Job %s failed:\n%s", job_id, traceback.format_exc())
            message = f"{type(exc).__name__}: {exc}"[:2000]

            def mark_failed(job: Job) -> None:
                job.status = JobStatus.FAILED
                job.error = message
                job.review_payload = None
                job.progress.current_node = None
                job.completed_at = utcnow()

            self._store.update(job_id, mark_failed)
        finally:
            with self._waiters_lock:
                self._waiters.pop(job_id, None)
            if holding_slot:
                self._slots.release()
