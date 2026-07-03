"""Facts Agent output schema.

Facts rarely sit under a single clean heading, so this is one of the agents that
leans on retrieval fallback. Timeline events are individually sourced.
"""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel, Field

from .base import Sourced, SourcedItem


class TimelineEvent(BaseModel):
    """A dated event in the chronology of the case."""

    event_date: date | None = None  # None when the doc gives an event but no firm date.
    description: str


class FactsOutput(BaseModel):
    """Structured output of the Facts Agent."""

    background: Sourced[str] = Field(default_factory=Sourced)
    incident_summary: Sourced[str] = Field(default_factory=Sourced)
    key_facts: list[SourcedItem[str]] = Field(default_factory=list)
    timeline: list[SourcedItem[TimelineEvent]] = Field(default_factory=list)
