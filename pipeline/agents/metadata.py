"""Metadata Agent — case-identifying header information."""

from __future__ import annotations

from schemas import MetadataOutput

from ..chunking import Chunk
from .base import build_context_text, run_structured_agent

SYSTEM_PROMPT = """You are the Metadata Agent for an Indian court judgment extraction system.

Extract only case-identifying header information:
- court: the court name (e.g. "Supreme Court of India", "High Court of Delhi")
- bench: the bench, if named (e.g. "Division Bench")
- judges: names of judges/justices who authored or joined the judgment
- decision_date: the date the judgment was delivered/decided
- case_number: the case/appeal/petition number as written
- petitioners: parties named as petitioner/appellant/plaintiff, with their role label as written
- respondents: parties named as respondent/defendant/state, with their role label as written
- jurisdiction: the territorial/subject-matter jurisdiction if stated

Do not extract facts, arguments, or statute citations here — those belong to other agents."""


def run(chunks: list[Chunk], *, temperature: float = 0.0) -> MetadataOutput:
    context = build_context_text(chunks)
    return run_structured_agent(MetadataOutput, SYSTEM_PROMPT, context, temperature=temperature)
