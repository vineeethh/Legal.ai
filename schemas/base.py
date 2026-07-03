"""Provenance primitives shared by every extracted field.

The `Sourced[T]` wrapper is the backbone of the whole system: it enforces that
*every* extracted value carries the verbatim source span it came from. That span is
what the validator checks against, what the confidence engine scores for coverage,
and what a lawyer clicks to jump back to the judgment.

Rule: an agent that cannot confidently extract a field returns `Sourced(value=None)`
(or the field is omitted) — it never fabricates a value or a source.
"""

from __future__ import annotations

from typing import Generic, Optional, TypeVar

from pydantic import BaseModel, ConfigDict, Field, model_validator

T = TypeVar("T")


class SourceRef(BaseModel):
    """A pointer back into the parsed judgment for one extracted value.

    `quote` is the *verbatim* text from the document that supports the value.
    It is mandatory: validation requires a literal span to check entailment against,
    and provenance without the actual text is not auditable.
    """

    model_config = ConfigDict(frozen=True)

    page: int = Field(..., ge=1, description="1-based page number in the source PDF.")
    quote: str = Field(..., min_length=1, description="Verbatim supporting span from the document.")
    char_start: Optional[int] = Field(
        default=None, ge=0, description="Char offset of the quote within the page/document text."
    )
    char_end: Optional[int] = Field(default=None, ge=0)
    chunk_id: Optional[str] = Field(
        default=None, description="Id of the chunk this span was retrieved/routed from."
    )
    section_path: Optional[str] = Field(
        default=None,
        description="Docling hierarchical path, e.g. 'ORDER > Held' — records how the chunk was routed.",
    )

    @model_validator(mode="after")
    def _check_offsets(self) -> "SourceRef":
        if (
            self.char_start is not None
            and self.char_end is not None
            and self.char_end < self.char_start
        ):
            raise ValueError("char_end must be >= char_start")
        return self


class Sourced(BaseModel, Generic[T]):
    """A single extracted value together with its provenance.

    `value is None` is a first-class, legitimate state meaning "not confidently found"
    — never an error and never a fabrication. When `value` is None, `sources` must be
    empty; when `value` is present, at least one `SourceRef` is required.
    """

    value: Optional[T] = None
    sources: list[SourceRef] = Field(default_factory=list)
    extraction_confidence: Optional[float] = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="Optional self-reported model confidence; NOT used for the deterministic score.",
    )

    @model_validator(mode="after")
    def _provenance_consistency(self) -> "Sourced[T]":
        if self.value is None and self.sources:
            raise ValueError("A None value must not carry sources.")
        if self.value is not None and not self.sources:
            raise ValueError("A non-None value must carry at least one SourceRef.")
        return self

    @property
    def is_present(self) -> bool:
        return self.value is not None


class SourcedList(BaseModel, Generic[T]):
    """A list of individually-sourced items (e.g., multiple key facts, arguments).

    An empty `items` list is meaningful: it says "the agent looked and found none",
    distinct from a scalar `Sourced(value=None)`.
    """

    items: list["SourcedItem[T]"] = Field(default_factory=list)

    def __len__(self) -> int:
        return len(self.items)


class SourcedItem(BaseModel, Generic[T]):
    """One element of a SourcedList — always carries its own provenance."""

    value: T
    sources: list[SourceRef] = Field(..., min_length=1)
    extraction_confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0)


# Resolve the forward reference in SourcedList.items.
SourcedList.model_rebuild()
