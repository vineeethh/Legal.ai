"""LangGraph shared state.

This is the object the supervisor threads through the graph. It is a *container*, not
a channel for cross-agent context: extraction agents read only their own routed inputs
(see `agent_inputs`) and write only their own slot. No agent reads another agent's
`agent_outputs` entry — only the validator, confidence engine, and Response Agent do.

Reducer note: agents run in parallel and each writes a distinct key, so per-agent dicts
use last-write-wins per key. When wiring into LangGraph, annotate the mutable dict
fields with an appropriate merge reducer (e.g. operator.or_) so concurrent writes merge
rather than clobber.
"""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field

from .arguments import ArgumentsOutput
from .confidence import ConfidenceBreakdown
from .enums import AgentName
from .evidence import EvidenceOutput
from .facts import FactsOutput
from .final import StructuredJudgment
from .metadata import MetadataOutput
from .statutes import StatuteOutput
from .validation import AgentValidationResult


class RoutedInput(BaseModel):
    """What a single extraction agent is allowed to see: its routed chunks + prompt id.

    Structure-first routing populates `chunk_ids` from Docling sections; the retrieval
    fallback appends reranked chunk ids when structure routing is thin.
    """

    agent: AgentName
    chunk_ids: list[str] = Field(default_factory=list)
    routed_by: str = Field(default="structure", description="'structure' | 'retrieval' | 'hybrid'.")
    prompt_version: str | None = None


class PipelineState(BaseModel):
    """Top-level graph state for one document run."""

    document_id: str
    source_path: str

    # Populated by parse/chunk/index nodes.
    chunk_count: int = 0
    ocr_used: bool = False

    # Per-agent isolated inputs (supervisor fills these before fan-out).
    agent_inputs: dict[AgentName, RoutedInput] = Field(default_factory=dict)

    # Raw extraction outputs (one slot per agent, written only by that agent).
    metadata: Optional[MetadataOutput] = None
    facts: Optional[FactsOutput] = None
    statutes: Optional[StatuteOutput] = None
    petitioner: Optional[ArgumentsOutput] = None
    respondent: Optional[ArgumentsOutput] = None
    evidence: Optional[EvidenceOutput] = None

    # Validation + retry bookkeeping.
    validations: dict[AgentName, AgentValidationResult] = Field(default_factory=dict)
    retry_counts: dict[AgentName, int] = Field(default_factory=dict)

    # Assembly + scoring.
    confidence: Optional[ConfidenceBreakdown] = None
    result: Optional[StructuredJudgment] = None

    # Free-form trace hooks (Langfuse span ids, timings) — not used for logic.
    trace: dict[str, Any] = Field(default_factory=dict)

    # Prompt-injection guardrail: chunk_id -> matched pattern names, populated
    # once at parse time (pipeline/injection_screen.py). Used for logic — see
    # assemble_node in pipeline/graph.py, which floors the review decision at
    # needs_review when this is non-empty.
    injection_matches: dict[str, list[str]] = Field(default_factory=dict)

    # PDF structural safety guardrail (pipeline/pdf_safety.py), populated by
    # the pdf_safety_gate node. Non-empty routes the graph straight to the
    # `rejected` terminal node — run_document() raises PdfSafetyError from it.
    pdf_safety_reasons: list[str] = Field(default_factory=list)
