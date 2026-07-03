"""Statute Agent output schema — the only agent that uses RAG.

Flow: the LLM extracts raw citations (with provenance) from the judgment, each is
parsed into (act, section), then cross-referenced against the Qdrant KB. The KB match
and the verdict are attached to each citation. RAG is used ONLY to verify — never to
generate or "enrich" the extraction.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from .base import SourceRef
from .enums import StatuteAct, VerificationStatus


class KBMatch(BaseModel):
    """The official statute record retrieved from the KB for a citation."""

    act: StatuteAct
    act_version: str = Field(..., description="e.g. 'IPC-1860' — matched against the correct act, not just a number.")
    section_number: str
    section_title: str | None = None
    official_text: str
    similarity_score: float = Field(..., ge=0.0, le=1.0, description="Reranker (bge-reranker-v2-m3) score.")


class StatuteReference(BaseModel):
    """One legal citation found in the judgment, plus its verification result."""

    # --- extracted from the judgment (with provenance) ---
    raw_citation: str = Field(..., description="Citation exactly as written, e.g. 'Section 302 IPC'.")
    parsed_act: StatuteAct = StatuteAct.UNKNOWN
    parsed_section: str | None = None
    sources: list[SourceRef] = Field(..., min_length=1)

    # --- verification (populated by the retriever step) ---
    verification_status: VerificationStatus = VerificationStatus.SKIPPED
    kb_match: KBMatch | None = None
    verification_note: str | None = None

    # --- crosswalk enrichment (never affects verification_status) ---
    current_equivalent: KBMatch | None = Field(
        default=None,
        description=(
            "Modern-act equivalent from the statute_mappings crosswalk (e.g. IPC 302 -> "
            "BNS 103), attached for convenience only. The citation is verified against "
            "the act actually cited, never silently substituted."
        ),
    )


class StatuteOutput(BaseModel):
    """Structured output of the Statute Agent."""

    references: list[StatuteReference] = Field(default_factory=list)

    @property
    def verified_count(self) -> int:
        return sum(1 for r in self.references if r.verification_status == VerificationStatus.VERIFIED)

    @property
    def verification_rate(self) -> float:
        """Fraction of citations that verified against the KB. Feeds the confidence score."""
        if not self.references:
            return 1.0  # nothing to verify is not a penalty
        return self.verified_count / len(self.references)
