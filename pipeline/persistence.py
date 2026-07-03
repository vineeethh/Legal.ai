"""Writes a completed run to Postgres (documents, processing_runs, validation_logs)."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import psycopg

from schemas import PipelineState

from .config import get_settings


def save_run(state: PipelineState, *, started_at: datetime, langfuse_session_id: str | None = None) -> str:
    """Persists the completed run; returns the processing_runs.id (UUID str)."""
    if state.result is None:
        raise ValueError("Cannot persist a run with no assembled result.")

    settings = get_settings()
    source_path = Path(state.source_path)

    with psycopg.connect(settings.database_url) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO documents (source_filename, page_count, ocr_used)
                VALUES (%s, %s, %s)
                RETURNING id
                """,
                (source_path.name, None, state.ocr_used),
            )
            document_id = cur.fetchone()[0]

            cur.execute(
                """
                INSERT INTO processing_runs
                    (document_id, structured_json, confidence_score, review_decision,
                     llm_model, prompt_versions, retry_counts, langfuse_session_id,
                     started_at, completed_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
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
                    langfuse_session_id,
                    started_at,
                    datetime.utcnow(),
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
