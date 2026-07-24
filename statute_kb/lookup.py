"""Two-tier statute verification.

Tier 1 (primary, deterministic): exact Postgres lookup on (act, section_number),
optionally filtered to the version in force on `as_of_date`. Cheap, exact, and
drives VERIFIED/NOT_FOUND for any well-formed citation.

Tier 2 (secondary, semantic): only used to (a) confirm quoted section text
actually matches canonical text (catches MISMATCH), or (b) attempt a fuzzy
Qdrant match when the citation didn't parse cleanly enough for tier 1 — which
is reported as NOT_FOUND with a note, never silently upgraded to VERIFIED,
since embedding similarity is not proof of citation correctness.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from qdrant_client import QdrantClient

from pipeline.config import get_settings
from schemas import KBMatch, StatuteAct, VerificationStatus

MISMATCH_SIMILARITY_THRESHOLD = 0.55


@dataclass
class VerificationResult:
    status: VerificationStatus
    kb_match: KBMatch | None
    note: str | None
    current_equivalent: KBMatch | None


def _row_to_kb_match(row: dict, similarity_score: float = 1.0) -> KBMatch:
    return KBMatch(
        act=StatuteAct(row["act"]),
        act_version=row["act_version"],
        section_number=row["section_number"],
        section_title=row["section_title"],
        official_text=row["content"],
        similarity_score=similarity_score,
    )


def _fetch_exact(cur, act: StatuteAct, section_number: str, as_of_date: date | None) -> dict | None:
    if as_of_date is not None:
        cur.execute(
            """
            SELECT * FROM statute_sections
            WHERE act = %s AND section_number = %s
              AND effective_from <= %s
              AND (effective_to IS NULL OR effective_to >= %s)
            ORDER BY effective_from DESC LIMIT 1
            """,
            (act.value, section_number, as_of_date, as_of_date),
        )
    else:
        cur.execute(
            """
            SELECT * FROM statute_sections
            WHERE act = %s AND section_number = %s
            ORDER BY effective_from DESC LIMIT 1
            """,
            (act.value, section_number),
        )
    return cur.fetchone()


def _fetch_current_equivalent(cur, act: StatuteAct, section_number: str) -> dict | None:
    cur.execute(
        """
        SELECT m.new_act, m.new_section, m.mapping_type
        FROM statute_mappings m
        WHERE m.old_act = %s AND m.old_section = %s AND m.new_section IS NOT NULL
        LIMIT 1
        """,
        (act.value, section_number),
    )
    mapping = cur.fetchone()
    if not mapping:
        return None
    cur.execute(
        "SELECT * FROM statute_sections WHERE act = %s AND section_number = %s ORDER BY effective_from DESC LIMIT 1",
        (mapping["new_act"], mapping["new_section"]),
    )
    return cur.fetchone()


def _semantic_fallback(
    client: QdrantClient, quoted_text: str, act_hint: StatuteAct | None
) -> tuple[dict | None, float]:
    from pipeline.embeddings import embed_texts

    settings = get_settings()
    query_filter = None
    if act_hint is not None and act_hint != StatuteAct.UNKNOWN:
        from qdrant_client.models import FieldCondition, Filter, MatchValue

        query_filter = Filter(must=[FieldCondition(key="act", match=MatchValue(value=act_hint.value))])

    vector = embed_texts([quoted_text])[0].tolist()
    hits = client.query_points(
        collection_name=settings.qdrant_collection,
        query=vector,
        query_filter=query_filter,
        limit=1,
    ).points
    if not hits:
        return None, 0.0
    return hits[0].payload, hits[0].score


def verify_citation(
    cur,
    qdrant_client: QdrantClient,
    *,
    parsed_act: StatuteAct,
    parsed_section: str | None,
    quoted_text: str | None = None,
    as_of_date: date | None = None,
) -> VerificationResult:
    """Verify one citation using a caller-provided Postgres cursor and Qdrant
    client, so a document's citations share one connection/client each rather
    than opening one per call (see pipeline/statute_verification.py)."""
    if parsed_section is None or parsed_act == StatuteAct.UNKNOWN:
        if quoted_text:
            payload, score = _semantic_fallback(
                qdrant_client, quoted_text, parsed_act if parsed_act != StatuteAct.UNKNOWN else None
            )
            if payload and score >= MISMATCH_SIMILARITY_THRESHOLD:
                return VerificationResult(
                    status=VerificationStatus.NOT_FOUND,
                    kb_match=None,
                    note=(
                        f"Citation could not be parsed to an exact section; closest semantic match was "
                        f"{payload['act']} s.{payload['section_number']} (score={score:.2f}) — not auto-verified."
                    ),
                    current_equivalent=None,
                )
        return VerificationResult(VerificationStatus.SKIPPED, None, "Citation act/section could not be parsed.", None)

    row = _fetch_exact(cur, parsed_act, parsed_section, as_of_date)

    if row is None:
        return VerificationResult(
            status=VerificationStatus.NOT_FOUND,
            kb_match=None,
            note=f"No KB entry for {parsed_act.value} section {parsed_section}.",
            current_equivalent=None,
        )

    kb_match = _row_to_kb_match(row)
    status = VerificationStatus.VERIFIED
    note = None

    if quoted_text:
        from pipeline.embeddings import get_reranker

        score = get_reranker().compute_score([[quoted_text, row["content"]]], normalize=True)
        score = score[0] if isinstance(score, list) else score
        if score < MISMATCH_SIMILARITY_THRESHOLD:
            status = VerificationStatus.MISMATCH
            note = f"Quoted text diverges from canonical section text (similarity={score:.2f})."
        kb_match = _row_to_kb_match(row, similarity_score=float(score))

    equiv_row = _fetch_current_equivalent(cur, parsed_act, parsed_section)
    current_equivalent = _row_to_kb_match(equiv_row) if equiv_row else None

    return VerificationResult(status=status, kb_match=kb_match, note=note, current_equivalent=current_equivalent)
