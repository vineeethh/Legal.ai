"""Read-only Postgres queries for the web API (listing documents, fetching
persisted results, KB stats). Writes stay in pipeline/persistence.py — this
module never mutates run data."""

from __future__ import annotations

import json
from typing import Any

import psycopg
from psycopg.rows import dict_row

from pipeline.config import get_settings


def _connect():
    return psycopg.connect(get_settings().database_url, row_factory=dict_row)


def list_documents() -> list[dict[str, Any]]:
    """Every persisted document with its latest run's score/decision."""
    with _connect() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT DISTINCT ON (d.id)
                   d.id::text AS id,
                   d.source_filename AS filename,
                   d.uploaded_at,
                   d.page_count,
                   d.ocr_used,
                   r.id::text AS run_id,
                   r.confidence_score AS confidence,
                   r.review_decision AS decision,
                   r.completed_at
            FROM documents d
            LEFT JOIN processing_runs r ON r.document_id = d.id
            ORDER BY d.id, r.created_at DESC
            """
        )
        rows = cur.fetchall()
    rows.sort(key=lambda r: r["uploaded_at"], reverse=True)
    for r in rows:
        r["uploaded_at"] = r["uploaded_at"].isoformat() if r["uploaded_at"] else None
        r["completed_at"] = r["completed_at"].isoformat() if r["completed_at"] else None
        r["status"] = "completed" if r["run_id"] else "unknown"
        r["source"] = "db"
    return rows


def get_document(document_id: str) -> dict[str, Any] | None:
    with _connect() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT d.id::text AS id, d.source_filename AS filename, d.uploaded_at,
                   d.page_count, d.ocr_used,
                   r.id::text AS run_id, r.confidence_score AS confidence,
                   r.review_decision AS decision, r.completed_at
            FROM documents d
            LEFT JOIN processing_runs r ON r.document_id = d.id
            WHERE d.id = %s
            ORDER BY r.created_at DESC
            LIMIT 1
            """,
            (document_id,),
        )
        row = cur.fetchone()
    if row is None:
        return None
    row["uploaded_at"] = row["uploaded_at"].isoformat() if row["uploaded_at"] else None
    row["completed_at"] = row["completed_at"].isoformat() if row["completed_at"] else None
    row["status"] = "completed" if row["run_id"] else "unknown"
    row["source"] = "db"
    return row


def get_result(document_id: str) -> dict[str, Any] | None:
    """Latest persisted StructuredJudgment for a document, or None."""
    with _connect() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT structured_json FROM processing_runs
            WHERE document_id = %s
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (document_id,),
        )
        row = cur.fetchone()
    if row is None:
        return None
    value = row["structured_json"]
    # psycopg returns JSONB as dict already; json column stored via json.dumps
    return value if isinstance(value, dict) else json.loads(value)


def get_validation_logs(document_id: str) -> list[dict[str, Any]]:
    """Validation log rows for a document's latest run (the audit trail)."""
    with _connect() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT v.agent, v.attempt, v.field_path, v.status, v.supporting_quote, v.reason
            FROM validation_logs v
            WHERE v.processing_run_id = (
                SELECT id FROM processing_runs
                WHERE document_id = %s
                ORDER BY created_at DESC LIMIT 1
            )
            ORDER BY v.id
            """,
            (document_id,),
        )
        return cur.fetchall()


def kb_search(query: str, act_version: str | None = None, limit: int = 20) -> list[dict[str, Any]]:
    """Simple KB lookup for the browser screen: exact section-number match is
    ranked first, then title/content ILIKE. Read-only, capped."""
    pattern = f"%{query}%"
    with _connect() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT act_version, section_number, section_title, chapter_path,
                   left(content, 400) AS snippet, status, effective_from, effective_to,
                   (section_number = %(q)s) AS exact
            FROM statute_sections
            WHERE (%(act)s::text IS NULL OR act_version = %(act)s)
              AND (section_number = %(q)s
                   OR section_title ILIKE %(pat)s
                   OR content ILIKE %(pat)s)
            ORDER BY exact DESC, act_version, length(section_number), section_number
            LIMIT %(limit)s
            """,
            {"q": query, "act": act_version, "pat": pattern, "limit": limit},
        )
        rows = cur.fetchall()
    for r in rows:
        r["effective_from"] = r["effective_from"].isoformat() if r["effective_from"] else None
        r["effective_to"] = r["effective_to"].isoformat() if r["effective_to"] else None
    return rows


def kb_stats() -> dict[str, Any]:
    """Section counts per act version — the dashboard's KB coverage strip."""
    with _connect() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT act_version, count(*) AS sections
            FROM statute_sections
            GROUP BY act_version
            ORDER BY act_version
            """
        )
        acts = cur.fetchall()
        cur.execute("SELECT count(*) AS n FROM statute_mappings")
        mappings = cur.fetchone()["n"]
        cur.execute("SELECT count(*) AS n FROM processing_runs")
        runs = cur.fetchone()["n"]
    return {
        "acts": acts,
        "total_sections": sum(a["sections"] for a in acts),
        "crosswalk_mappings": mappings,
        "total_runs": runs,
    }
