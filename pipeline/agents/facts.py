"""Facts Agent — case background, incident summary, chronology."""

from __future__ import annotations

from schemas import FactsOutput

from ..chunking import Chunk
from .base import build_context_text, run_structured_agent

SYSTEM_PROMPT = """You are the Facts Agent for an Indian court judgment extraction system.

Extract:
- background: general background/context of the dispute or prosecution
- incident_summary: a summary of the core incident giving rise to the case
- key_facts: a list of individually-sourced discrete facts material to the case
- timeline: dated events in chronological order (event_date may be omitted if the
  document gives an event without a firm date)

Do not extract arguments, statute citations, or evidence details here — those
belong to other agents. Only extract facts as stated in the judgment; do not
infer or summarize beyond what's written."""


def run(chunks: list[Chunk], *, temperature: float = 0.0) -> FactsOutput:
    context = build_context_text(chunks)
    return run_structured_agent(FactsOutput, SYSTEM_PROMPT, context, temperature=temperature)
