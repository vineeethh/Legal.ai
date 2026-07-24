"""Writes a completed run to Postgres (documents, processing_runs, validation_logs)."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import psycopg

from schemas import PipelineState

from .config import get_settings


def save_run(
    state: PipelineState,
    *,
    started_at: datetime,
    langfuse_session_id: str | None = None,
    human_review_decision: dict | None = None,
    source_filename: str | None = None,
) -> str:
    """Persists the completed run; returns the processing_runs.id (UUID str).

    `source_filename` preserves the user's original upload name — web uploads
    are stored on disk as {document_id}.pdf, so the on-disk name is not the
    display name. Defaults to the stored file's basename (the CLI path)."""
    if state.result is None:
        raise ValueError("Cannot persist a run with no assembled result.")

    settings = get_settings()
    source_path = Path(state.source_path)

    with psycopg.connect(settings.database_url) as conn:
        with conn.cursor() as cur:
            # Use the run's own document_id as the documents PK so the persisted
            # row, the LangGraph checkpoint thread_id, and the Langfuse session
            # all share one id (previously this row got a fresh gen_random_uuid,
            # so a saved record couldn't be joined to its trace/checkpoint).
            cur.execute(
                """
                INSERT INTO documents (id, source_filename, page_count, ocr_used)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (id) DO UPDATE SET
                    source_filename = EXCLUDED.source_filename,
                    page_count = EXCLUDED.page_count,
                    ocr_used = EXCLUDED.ocr_used
                RETURNING id
                """,
                (state.document_id, source_filename or source_path.name, state.page_count, state.ocr_used),
            )
            document_id = cur.fetchone()[0]

            cur.execute(
                """
                INSERT INTO processing_runs
                    (document_id, structured_json, confidence_score, review_decision,
                     llm_model, prompt_versions, retry_counts, human_review_decision,
                     langfuse_session_id, started_at, completed_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id
                """,
                (
                    document_id,
                    json.dumps(state.result.model_dump(mode="json")),
                    state.result.confidence.score,
                    state.result.review_decision.value,
                    state.result.processing.llm_model,
                    json.dumps(state.result.processing.prompt_versions),
                    json.dumps({k.value: v for k, v in state.retry_counts.items()}),
                    json.dumps(human_review_decision) if human_review_decision is not None else None,
                    langfuse_session_id,
                    started_at,
                    datetime.now(timezone.utc),
                ),
            )
            run_id = cur.fetchone()[0]

            for agent, validation in state.validations.items():
                for field in validation.fields:
                    cur.execute(
                        """
                        INSERT INTO validation_logs
                            (processing_run_id, agent, attempt, field_path, status,
                             supporting_quote, reason)
                        VALUES (%s, %s, %s, %s, %s, %s, %s)
                        """,
                        (
                            run_id,
                            agent.value,
                            validation.attempt,
                            field.field_path,
                            field.status.value,
                            field.supporting_quote,
                            field.reason,
                        ),
                    )

        conn.commit()

    return str(run_id)
