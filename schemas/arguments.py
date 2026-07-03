"""Petitioner Agent and Respondent Agent output schemas.

Both agents share the same shape but run in complete isolation from each other — the
Respondent Agent never sees the petitioner's arguments and vice versa. This prevents
one side's framing from contaminating the other's extraction.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from .base import SourcedItem


class Argument(BaseModel):
    """A single argument advanced by a party."""

    summary: str
    # Optional statute/precedent the argument leans on, as written in the judgment.
    relied_on: str | None = None


class ArgumentsOutput(BaseModel):
    """Shared output shape for the Petitioner and Respondent agents.

    `party_side` records which agent produced it, purely for logging/assembly — the
    agents themselves remain single-purpose and isolated.
    """

    party_side: str = Field(..., description="'petitioner' or 'respondent'.")
    arguments: list[SourcedItem[Argument]] = Field(default_factory=list)
