"""Evidence Agent — witnesses, exhibits, physical/digital evidence."""

from __future__ import annotations

from schemas import AgentName, EvidenceOutput

from ..chunking import Chunk
from ..prompt_spec import PromptSpec
from .base import build_context_text, run_structured_agent

SYSTEM_PROMPT = """You are the Evidence Agent for an Indian court judgment extraction system.

Extract every piece of evidence referenced in the excerpt, classified as one of:
witness, document, physical, digital. Include the label as written if given (e.g.
witness label "PW-1", exhibit number "Ext. P-12"). Do not extract facts or
arguments about the evidence's weight or credibility — only what evidence was
presented, as stated."""


def run(chunks: list[Chunk], **llm_kwargs) -> EvidenceOutput:
    context = build_context_text(chunks)
    return run_structured_agent(EvidenceOutput, SYSTEM_PROMPT, context, **llm_kwargs)


PROMPT_SPECS: dict[AgentName, PromptSpec] = {
    AgentName.EVIDENCE: PromptSpec(node="evidence", system_prompt=SYSTEM_PROMPT),
}
