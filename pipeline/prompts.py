"""Prompt registry — aggregates references to each agent's prompt text.

Prompt text itself is never moved here: it stays in each agent module (that's
still the one place to edit a prompt). This module only collects `PromptSpec`
entries that agent modules export, so the architecture doc generator
(pipeline/architecture_doc.py) can enumerate every node's prompt in one place.
"""

from __future__ import annotations

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
