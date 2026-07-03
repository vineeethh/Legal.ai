"""Petitioner and Respondent Agents — same shape, run in complete isolation
from each other (each only ever sees chunks routed to it, never the other
side's routed input or output)."""

from __future__ import annotations

from schemas import ArgumentsOutput

from ..chunking import Chunk
from .base import build_context_text, run_structured_agent

SYSTEM_PROMPT_TEMPLATE = """You are the {side_title} Agent for an Indian court judgment extraction system.

Extract only arguments/submissions made BY THE {side_upper} (or their counsel), as
recorded in the excerpt. For each argument, give a concise summary and, if the
argument leans on a specific statute or precedent, record it in `relied_on` exactly
as written.

Do not extract the other party's arguments, facts, or evidence — only what this
excerpt attributes to the {side_lower}."""


def _run(side: str, chunks: list[Chunk], *, temperature: float = 0.0) -> ArgumentsOutput:
    context = build_context_text(chunks)
    prompt = SYSTEM_PROMPT_TEMPLATE.format(
        side_title=side.capitalize(), side_upper=side.upper(), side_lower=side
    )
    result = run_structured_agent(ArgumentsOutput, prompt, context, temperature=temperature)
    if result.party_side != side:
        result = result.model_copy(update={"party_side": side})
    return result


def run_petitioner(chunks: list[Chunk], *, temperature: float = 0.0) -> ArgumentsOutput:
    return _run("petitioner", chunks, temperature=temperature)


def run_respondent(chunks: list[Chunk], *, temperature: float = 0.0) -> ArgumentsOutput:
    return _run("respondent", chunks, temperature=temperature)
