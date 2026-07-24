"""Prompt registry — aggregates references to each agent's prompt text.

Prompt text itself is never moved here: it stays in each agent module (that's
still the one place to edit a prompt). This module only collects `PromptSpec`
entries that agent modules export, so the architecture doc generator
(pipeline/architecture_doc.py) can enumerate every node's prompt in one place.
"""

from __future__ import annotations

import hashlib

from schemas import AgentName

from .agents import arguments as arguments_agent
from .agents import evidence as evidence_agent
from .agents import facts as facts_agent
from .agents import metadata as metadata_agent
from .agents import statute as statute_agent
from .prompt_spec import PromptSpec

AGENT_PROMPTS: dict[AgentName, PromptSpec] = {}
for _module in (metadata_agent, facts_agent, statute_agent, arguments_agent, evidence_agent):
    AGENT_PROMPTS.update(_module.PROMPT_SPECS)
del _module


def prompt_versions() -> dict[str, str]:
    """Map each agent name -> a short stable hash of its system prompt.

    Stored in ProcessingMetadata.prompt_versions so a persisted record pins the
    exact prompt text it was produced with (reproducibility/audit). A prompt
    edit changes the hash, so two runs are comparable only when the hashes match.
    """
    return {
        agent.value: hashlib.sha256(spec.system_prompt.encode("utf-8")).hexdigest()[:12]
        for agent, spec in AGENT_PROMPTS.items()
    }
