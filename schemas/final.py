"""Unified structured judgment — the Response Agent's output and the DB record.

The Response Agent performs NO extraction. It composes already-validated agent outputs
into this single document, attaches the deterministic confidence breakdown and the
processing metadata needed for audit/reproducibility.
"""

from __future__ import annotations

from datetime import datetime, timezone

from pydantic import BaseModel, Field

from .arguments import ArgumentsOutput
from .confidence import ConfidenceBreakdown
from .enums import ReviewDecision
from .evidence import EvidenceOutput
from .facts import FactsOutput
from .metadata import MetadataOutput
from .statutes import StatuteOutput


class ProcessingMetadata(BaseModel):
    """Audit trail for reproducibility — the 'how this record was produced' block."""

    document_id: str
    schema_version: str = "1.0.0"
    llm_model: str
    prompt_versions: dict[str, str] = Field(
        default_factory=dict, description="agent name -> prompt hash used, for reproducibility."
    )
    retry_counts: dict[str, int] = Field(default_factory=dict, description="agent name -> retries used.")
    agent_errors: dict[str, str] = Field(
        default_factory=dict,
        description=(
            "agent name -> exception message from its last failed attempt, present only "
            "for agents that exhausted retries and degraded to an empty output. "
            "Distinguishes 'the model/endpoint is broken' from 'nothing was found'."
        ),
    )
    processed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    duration_seconds: float | None = None


class StructuredJudgment(BaseModel):
    """The final artifact stored in PostgreSQL and returned by the API."""

    metadata: MetadataOutput
    facts: FactsOutput
    statutes: StatuteOutput
    petitioner: ArgumentsOutput
    respondent: ArgumentsOutput
    evidence: EvidenceOutput

    confidence: ConfidenceBreakdown
    review_decision: ReviewDecision
    processing: ProcessingMetadata
