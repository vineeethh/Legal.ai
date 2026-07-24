"""Wires the Statute Agent's raw output to statute_kb.lookup — the only place
this pipeline touches the KB. Runs after the Statute Agent, before validation."""

from __future__ import annotations

from datetime import date

import psycopg
from psycopg.rows import dict_row
from qdrant_client import QdrantClient

from schemas import StatuteOutput

from pipeline.config import get_settings
from statute_kb.lookup import verify_citation


def verify_statute_output(statute_output: StatuteOutput, *, as_of_date: date | None = None) -> StatuteOutput:
    if not statute_output.references:
        return statute_output

    settings = get_settings()
    verified_refs = []
    # One Postgres connection + one Qdrant client for the whole document's
    # citations, instead of opening one of each per verify_citation call.
    with psycopg.connect(settings.database_url, row_factory=dict_row) as conn:
        with conn.cursor() as cur:
            qdrant_client = QdrantClient(url=settings.qdrant_url, api_key=settings.qdrant_api_key or None)
            for ref in statute_output.references:
                quoted_text = ref.sources[0].quote if ref.sources else None
                result = verify_citation(
                    cur,
                    qdrant_client,
                    parsed_act=ref.parsed_act,
                    parsed_section=ref.parsed_section,
                    quoted_text=quoted_text,
                    as_of_date=as_of_date,
                )
                verified_refs.append(
                    ref.model_copy(
                        update={
                            "verification_status": result.status,
                            "kb_match": result.kb_match,
                            "verification_note": result.note,
                            "current_equivalent": result.current_equivalent,
                        }
                    )
                )
    return statute_output.model_copy(update={"references": verified_refs})
