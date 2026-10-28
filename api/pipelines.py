"""Adapters between an API job and a pipeline implementation.

`RealPipeline` calls the existing LangGraph pipeline (pipeline.graph.run_document)
unchanged; heavy imports (Docling, FlagEmbedding, LangChain) happen inside its
methods so importing the API never needs them. `DemoPipeline` (api/demo.py)
implements the same interface without any of those dependencies.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Protocol

from .jobs import Job

ProgressFn = Callable[[str, dict], None]
ReviewFn = Callable[[dict], dict]


class DocumentRejected(Exception):
    """The PDF failed the structural safety scan; `reasons` lists every failed check."""

    def __init__(self, reasons: list[str]):
        self.reasons = reasons
        super().__init__("; ".join(reasons))


@dataclass
class PipelineOutcome:
    result: dict[str, Any]  # StructuredJudgment as JSON
    human_review_decision: dict | None
    processing_run_id: str | None


class Pipeline(Protocol):
    def check_ready(self) -> None: ...

    def run(self, job: Job, on_progress: ProgressFn, on_review: ReviewFn) -> PipelineOutcome: ...


class RealPipeline:
    def __init__(self, *, save_to_db: bool):
        self.save_to_db = save_to_db

    def check_ready(self) -> None:
        """Fails at API startup (not on the first upload) if required env vars are missing."""
        from observability import verify_langfuse_connection
        from pipeline.config import get_settings

        get_settings()
        verify_langfuse_connection()

    def run(self, job: Job, on_progress: ProgressFn, on_review: ReviewFn) -> PipelineOutcome:
        from observability import traced_run_config
        from pipeline.graph import run_document
        from pipeline.pdf_safety import PdfSafetyError
        from pipeline.persistence import save_run

        started_at = datetime.now(timezone.utc).replace(tzinfo=None)
        # job.id doubles as the LangGraph thread id and the Langfuse session id.
        run_config = traced_run_config(session_id=job.id, tags=["api"])
        try:
            state, decision = run_document(
                job.id,
                job.pdf_path,
                run_config=run_config,
                on_human_review=on_review,
                on_progress=on_progress,
            )
        except PdfSafetyError as exc:
            raise DocumentRejected(exc.reasons) from exc

        run_id = None
        if self.save_to_db:
            run_id = save_run(
                state,
                started_at=started_at,
                langfuse_session_id=job.id,
                human_review_decision=decision,
            )
        return PipelineOutcome(
            result=state.result.model_dump(mode="json"),
            human_review_decision=decision,
            processing_run_id=run_id,
        )
