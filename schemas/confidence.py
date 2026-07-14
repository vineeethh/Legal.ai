"""Deterministic confidence scoring.

No LLM is involved. The final score is a weighted sum of measurable signals, then
mapped to a review decision by fixed thresholds. Weights and thresholds live here so
scoring is config-driven and auditable.
"""

from __future__ import annotations

from pydantic import BaseModel, Field, model_validator

from .enums import ReviewDecision


class ConfidenceWeights(BaseModel):
    """Relative weights of each signal. Must sum to 1.0."""

    validation_pass_rate: float = 0.35
    statute_verification_rate: float = 0.20
    provenance_coverage: float = 0.20
    schema_completeness: float = 0.15
    cross_agent_consistency: float = 0.10

    @model_validator(mode="after")
    def _sums_to_one(self) -> "ConfidenceWeights":
        total = (
            self.validation_pass_rate
            + self.statute_verification_rate
            + self.provenance_coverage
            + self.schema_completeness
            + self.cross_agent_consistency
        )
        if abs(total - 1.0) > 1e-6:
            raise ValueError(f"Confidence weights must sum to 1.0, got {total}")
        return self


class ConfidenceBreakdown(BaseModel):
    """The individual [0,1] signals plus the resulting score and decision.

    Signals:
    - validation_pass_rate: mean of per-agent field pass rates.
    - statute_verification_rate: fraction of citations VERIFIED against the KB.
    - provenance_coverage: fraction of present fields carrying >=1 valid SourceRef.
    - schema_completeness: fraction of expected required fields that are non-None.
    - cross_agent_consistency: deterministic checks across agents (e.g. parties in
      Metadata also appear in the arguments; decision date precedes no future events).
    """

    validation_pass_rate: float = Field(..., ge=0.0, le=1.0)
    statute_verification_rate: float = Field(..., ge=0.0, le=1.0)
    provenance_coverage: float = Field(..., ge=0.0, le=1.0)
    schema_completeness: float = Field(..., ge=0.0, le=1.0)
    cross_agent_consistency: float = Field(..., ge=0.0, le=1.0)

    score: float = Field(..., ge=0.0, le=1.0)
    decision: ReviewDecision

    @staticmethod
    def decide(score: float) -> ReviewDecision:
        if score >= 0.90:
            return ReviewDecision.AUTO_SAVE
        if score >= 0.80:
            return ReviewDecision.NEEDS_REVIEW
        return ReviewDecision.HUMAN_REQUIRED
