"""Evidence Agent output schema.

Groups evidence into the four kinds. Each item is individually sourced so a lawyer can
trace any listed exhibit or witness back to the exact page.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from .base import SourcedItem
from .enums import EvidenceKind


class EvidenceItem(BaseModel):
    """A single piece of evidence referenced in the judgment."""

    kind: EvidenceKind
    description: str
    # e.g. witness label 'PW-1', exhibit number 'Ext. P-12' — as written.
    label: str | None = None


class EvidenceOutput(BaseModel):
    """Structured output of the Evidence Agent.

    Kept as one flat sourced list keyed by `kind` rather than four parallel lists —
    simpler to validate and score, and trivial to group at assembly time.
    """

    items: list[SourcedItem[EvidenceItem]] = Field(default_factory=list)

    def of_kind(self, kind: EvidenceKind) -> list[SourcedItem[EvidenceItem]]:
        return [it for it in self.items if it.value.kind == kind]
