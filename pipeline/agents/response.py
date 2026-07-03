"""Response Agent — assembly only, no LLM call and no extraction.

Composes the already-validated agent outputs plus the confidence breakdown
into the final StructuredJudgment. Fields left as None after retries are
passed through as None — this agent never fills gaps.
"""

from __future__ import annotations

from schemas import (
    ArgumentsOutput,
    ConfidenceBreakdown,
    EvidenceOutput,
    FactsOutput,
    MetadataOutput,
    ProcessingMetadata,
    StatuteOutput,
    StructuredJudgment,
)


def assemble(
    *,
    metadata: MetadataOutput,
    facts: FactsOutput,
    statutes: StatuteOutput,
    petitioner: ArgumentsOutput,
    respondent: ArgumentsOutput,
    evidence: EvidenceOutput,
    confidence: ConfidenceBreakdown,
    processing: ProcessingMetadata,
) -> StructuredJudgment:
    return StructuredJudgment(
        metadata=metadata,
        facts=facts,
        statutes=statutes,
        petitioner=petitioner,
        respondent=respondent,
        evidence=evidence,
        confidence=confidence,
        review_decision=confidence.decision,
        processing=processing,
    )
