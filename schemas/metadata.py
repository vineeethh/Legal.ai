"""Metadata Agent output schema.

Extracts case-identifying header information. Every field is `Sourced` so a missing
judge name is an explicit `value=None`, never a guess.
"""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel, Field

from .base import Sourced, SourcedItem


class Party(BaseModel):
    """A named party. `role` is the label as it appears (petitioner/appellant/etc.)."""

    name: str
    role: str | None = None


class MetadataOutput(BaseModel):
    """Structured output of the Metadata Agent."""

    court: Sourced[str] = Field(default_factory=Sourced)
    bench: Sourced[str] = Field(default_factory=Sourced)
    judges: list[SourcedItem[str]] = Field(default_factory=list)
    decision_date: Sourced[date] = Field(default_factory=Sourced)
    case_number: Sourced[str] = Field(default_factory=Sourced)
    petitioners: list[SourcedItem[Party]] = Field(default_factory=list)
    respondents: list[SourcedItem[Party]] = Field(default_factory=list)
    jurisdiction: Sourced[str] = Field(default_factory=Sourced)
