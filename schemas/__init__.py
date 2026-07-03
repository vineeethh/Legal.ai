"""Pydantic contract layer for the Legal AI pipeline.

Every module depends on these types. Import from here rather than submodules so the
public surface stays stable as internals move.
"""

from __future__ import annotations

from .arguments import Argument, ArgumentsOutput
from .base import Sourced, SourcedItem, SourcedList, SourceRef
from .confidence import ConfidenceBreakdown, ConfidenceWeights
from .enums import (
    ACT_FAMILY,
    ActFamily,
    AgentName,
    EvidenceKind,
    ReviewDecision,
    StatuteAct,
    ValidationStatus,
    VerificationStatus,
)
from .evidence import EvidenceItem, EvidenceOutput
from .facts import FactsOutput, TimelineEvent
from .final import ProcessingMetadata, StructuredJudgment
from .metadata import MetadataOutput, Party
from .state import PipelineState, RoutedInput
from .statutes import KBMatch, StatuteOutput, StatuteReference
from .validation import AgentValidationResult, FieldValidation

__all__ = [
    # base / provenance
    "SourceRef",
    "Sourced",
    "SourcedItem",
    "SourcedList",
    # enums
    "ACT_FAMILY",
    "ActFamily",
    "AgentName",
    "EvidenceKind",
    "ReviewDecision",
    "StatuteAct",
    "ValidationStatus",
    "VerificationStatus",
    # agent outputs
    "MetadataOutput",
    "Party",
    "FactsOutput",
    "TimelineEvent",
    "StatuteOutput",
    "StatuteReference",
    "KBMatch",
    "ArgumentsOutput",
    "Argument",
    "EvidenceOutput",
    "EvidenceItem",
    # validation
    "AgentValidationResult",
    "FieldValidation",
    # confidence
    "ConfidenceBreakdown",
    "ConfidenceWeights",
    # final + state
    "StructuredJudgment",
    "ProcessingMetadata",
    "PipelineState",
    "RoutedInput",
]
