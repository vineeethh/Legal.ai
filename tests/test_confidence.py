"""Confidence engine — minimum-evidence floor.

Regression for the empirically-observed bug: an essentially empty extraction
scored 0.85 (needs_review) because four of the five signals default to 1.0 when
there is nothing to measure. A record with none of the core identifying fields
must floor to human_required.

Pure (schemas only) — runs on the bare interpreter, no langchain/docling needed.
"""

from __future__ import annotations

from datetime import date

import pytest

from pipeline.confidence import compute_confidence
from schemas import (
    ArgumentsOutput,
    EvidenceOutput,
    FactsOutput,
    MetadataOutput,
    ReviewDecision,
    Sourced,
    SourceRef,
    StatuteOutput,
)


def _empty_kwargs() -> dict:
    return dict(
        metadata=MetadataOutput(),
        facts=FactsOutput(),
        statutes=StatuteOutput(),
        petitioner=ArgumentsOutput(party_side="petitioner"),
        respondent=ArgumentsOutput(party_side="respondent"),
        evidence=EvidenceOutput(),
        validations={},
    )


def _src(quote: str) -> list[SourceRef]:
    return [SourceRef(page=1, quote=quote, chunk_id="c1")]


def test_empty_extraction_scores_high_but_is_floored_to_human_required():
    c = compute_confidence(**_empty_kwargs())
    # The raw score still lands in the inflated band (documents the underlying
    # signal behaviour) ...
    assert c.schema_completeness == 0.0
    assert c.score == pytest.approx(0.85)
    # ... but the floor overrides the decision.
    assert c.decision == ReviewDecision.HUMAN_REQUIRED


def test_record_with_core_fields_is_not_floored():
    kwargs = _empty_kwargs()
    kwargs["metadata"] = MetadataOutput(
        court=Sourced(value="High Court of X", sources=_src("High Court of X")),
        decision_date=Sourced(value=date(2024, 7, 31), sources=_src("31 July 2024")),
        case_number=Sourced(value="CRP 123/2024", sources=_src("CRP 123/2024")),
    )
    c = compute_confidence(**kwargs)
    assert c.schema_completeness == 1.0
    assert c.decision != ReviewDecision.HUMAN_REQUIRED  # floor does not fire


def test_partial_core_fields_not_floored():
    # Even one core field present means schema_completeness > 0, so the empty
    # floor does not apply; the normal thresholds decide.
    kwargs = _empty_kwargs()
    kwargs["metadata"] = MetadataOutput(
        case_number=Sourced(value="CRP 123/2024", sources=_src("CRP 123/2024")),
    )
    c = compute_confidence(**kwargs)
    assert c.schema_completeness == pytest.approx(1 / 3)
    # Not force-floored by the empty guardrail (decision follows the score).
    assert c.decision == c.decide(c.score)
