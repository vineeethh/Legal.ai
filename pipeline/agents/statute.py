"""Statute Agent — extracts raw legal citations only.

This agent does NOT verify citations — it only extracts what's written, with
provenance. Verification against the KB happens afterward in
statute_kb/lookup.py, which is the only place RAG touches this pipeline.
"""

from __future__ import annotations

from schemas import StatuteOutput

from ..chunking import Chunk
from .base import build_context_text, run_structured_agent

SYSTEM_PROMPT = """You are the Statute Agent for an Indian court judgment extraction system.

Extract every legal citation exactly as written in the excerpt — section/article
numbers, the act they're attributed to (as named or implied in the text), and the
verbatim citation text (e.g. "Section 302 IPC", "Article 21 of the Constitution",
"Section 103 BNS").

Leave parsed_act as UNKNOWN if the act cannot be confidently determined from this
excerpt alone — do not guess an act. Do not attempt to verify whether the citation
is correct; that happens in a separate step. Do not extract facts or arguments here."""


def run(chunks: list[Chunk], *, temperature: float = 0.0) -> StatuteOutput:
    context = build_context_text(chunks)
    return run_structured_agent(StatuteOutput, SYSTEM_PROMPT, context, temperature=temperature)
